"""Tests for what the sandbox-container sweep writes to the dispatch journal.

The journal is the only durable account of this lane. A reclaim removes a
container and a `docker ps` afterwards shows nothing — which is also what a
host that never leaked one shows — so without a record there is no way to
tell a working sweep from a sweep that never ran, and no way at all to
reconstruct how much of the slice's envelope came back.

EVERY EXPECTED STAGE NAME IS SPELLED AS A LITERAL HERE and bound to the
module's exported constant with one assertion. This file's Red predates
those constants, so importing them would make the Red a collection error
rather than a failed assertion — the same reason
`test_dispatcher_reconcile_supersession.py` spells its hold stage out.

A HELD container gets a record of its own, and that is not symmetry for its
own sake: "removes every terminal run's container and leaves every live one"
is a claim about both halves, and only the held records evidence the second.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_containers import (
    pass_container_sweeps,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import (
    SandboxContainerPort,
)

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RECLAIM_MODULE = f"{_PACKAGE}._dispatcher_sandbox_container_reclaim"

# The three stage names, as literals. See the module docstring.
_RECLAIMED_STAGE = "sandbox-container-reclaimed"
_HELD_STAGE = "sandbox-container-held"
_SWEEP_STAGE = "sandbox-container-sweep"
_STAGE_CONSTANTS = {
    "JOURNAL_STAGE_CONTAINER_RECLAIMED": _RECLAIMED_STAGE,
    "JOURNAL_STAGE_CONTAINER_HELD": _HELD_STAGE,
    "JOURNAL_STAGE_CONTAINER_SWEEP": _SWEEP_STAGE,
}

_TERMINAL_RUN = "01M4RM5YPANB7A4900404SEZXY"
_LIVE_RUN = "01M4SK59TGF6Q0CX3A1FV0Q5QE"
_LIMIT = 4294967296
_PS_STDOUT = f"fabro-run-{_TERMINAL_RUN}\nfabro-run-{_LIVE_RUN}\n"
_INSPECT_STDOUT = f"/fabro-run-{_TERMINAL_RUN}\t{_LIMIT}\n/fabro-run-{_LIVE_RUN}\t{_LIMIT}\n"
_STATUSES = {_TERMINAL_RUN: "failed", _LIVE_RUN: "running"}

# The daemon every port in this file is opened onto. The sweep addresses the
# surveyed FACTORY's daemon rather than the reconciling host's, so a port
# cannot be built without naming one.
_DOCKER_HOST = "ssh://cwoolley@hp-xubuntu.example"
_HP = FactoryTarget(
    name="hp",
    server="https://hp-xubuntu.example:32276",
    dev_token=None,
    docker_host=_DOCKER_HOST,
)


@dataclass(kw_only=True)
class _Docker:
    """One fake `docker` CLI, keyed by the verb the argv names.

    The verb is MEMBERSHIP-tested rather than read at a fixed index: every
    argv now opens with the global `--host <daemon>` pair, so an index-keyed
    fake would read the daemon address as the verb and answer every call the
    same way.
    """

    ps_stdout: str = ""
    ps_exit_code: int = 0
    inspect_stdout: str = ""
    rm_exit_code: int = 0
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
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if "ps" in argv:
            return CommandResult(exit_code=self.ps_exit_code, stdout=self.ps_stdout, stderr="")
        if "inspect" in argv:
            return CommandResult(exit_code=0, stdout=self.inspect_stdout, stderr="")
        return CommandResult(exit_code=self.rm_exit_code, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    written: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.written.append(record)


def _reclaim_module() -> Any:
    """Import the reclaim module, having first bound every stage name it owes."""
    module = importlib.import_module(_RECLAIM_MODULE)
    for name, expected in _STAGE_CONSTANTS.items():
        assert getattr(module, name, None) == expected, f"{name} is not {expected!r}"
    return module


def _journalled(
    *,
    runner: _Docker,
    tmp_path: Path,
    status_by_run: dict[str, str],
    dry_run: bool = False,
) -> list[dict[str, object]]:
    """Sweep, record it, and hand back exactly what reached the journal."""
    module = _reclaim_module()
    journal = _Journal()
    sweep = module.reclaim_terminal_run_containers(
        port=SandboxContainerPort(runner=runner, cwd=tmp_path, docker_host=_DOCKER_HOST),
        status_by_run=status_by_run,
        dry_run=dry_run,
    )
    if not dry_run:
        module.journal_container_sweep(journal=journal, sweep=sweep)
    return journal.written


def _record(*, records: list[dict[str, object]], stage: str) -> dict[str, object]:
    matching = [record for record in records if record["stage"] == stage]
    assert len(matching) == 1, f"expected exactly one {stage} record, got {len(matching)}"
    return matching[0]


def _inputs(*, tmp_path: Path, runner: _Docker, journal: _Journal) -> ReconcileInputs:
    """A reconcile bundle whose ONLY live seam is the one under test.

    The ledger is the package's own in-memory client rather than a fake with
    no caller: this lane never writes a comment, and a double whose methods
    nothing reaches is dead weight that reads as coverage.
    """
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=(),
        journaled=journaled_runs(text=""),
        runner=runner,
        journal=journal,
        ledger=FakeBeadsClient(),
    )


def test_a_reclaimed_containers_record_names_the_four_things_it_owes(tmp_path: Path) -> None:
    """The acceptance assertion, field by field.

    The container, its run id, that run's TERMINAL STATUS — the reading that
    authorised the removal — and the memory limit the host got back.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    records = _journalled(runner=runner, tmp_path=tmp_path, status_by_run=_STATUSES)

    reclaimed = _record(records=records, stage=_RECLAIMED_STAGE)
    assert reclaimed["container_name"] == f"fabro-run-{_TERMINAL_RUN}"
    assert reclaimed["run_id"] == _TERMINAL_RUN
    assert reclaimed["run_status_kind"] == "failed"
    assert reclaimed["memory_limit_bytes"] == _LIMIT
    assert reclaimed["removed"] is True


def test_a_held_container_is_recorded_with_the_reading_that_spared_it(tmp_path: Path) -> None:
    """The other half of the claim: the live container was seen and left alone."""
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    records = _journalled(runner=runner, tmp_path=tmp_path, status_by_run=_STATUSES)

    held = _record(records=records, stage=_HELD_STAGE)
    assert held["container_name"] == f"fabro-run-{_LIVE_RUN}"
    assert (held["run_id"], held["run_status_kind"]) == (_LIVE_RUN, "running")
    assert held["hold_reason"] == "run-live"
    assert held["memory_limit_bytes"] == _LIMIT


def test_the_pass_record_totals_what_the_sweep_did_and_what_it_reclaimed(
    tmp_path: Path,
) -> None:
    """One record per pass, so a sweep that found nothing still leaves a trace.

    It is written LAST, after the per-container records it summarises, and it
    counts a refused removal separately from a reclaimed one.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    records = _journalled(runner=runner, tmp_path=tmp_path, status_by_run=_STATUSES)

    assert [record["stage"] for record in records] == [
        _RECLAIMED_STAGE,
        _HELD_STAGE,
        _SWEEP_STAGE,
    ]
    summary = _record(records=records, stage=_SWEEP_STAGE)
    assert summary["inventory_observed"] is True
    assert summary["containers_observed"] == 2
    assert summary["containers_removed"] == 1
    assert summary["containers_remove_failed"] == 0
    assert summary["containers_held"] == 1
    assert summary["memory_limit_bytes_reclaimed"] == _LIMIT
    assert summary["reclaimed_limits_unmeasured"] == 0


def test_the_pass_record_names_the_factory_host_whose_daemon_it_inventoried(
    tmp_path: Path,
) -> None:
    """The acceptance assertion: whose inventory is this a record of?

    One pass writes one sweep record per surveyed factory daemon, and every
    field those records carry — the counts, the reclaimed bytes,
    `inventory_observed` — is a measurement of ONE host. Without the daemon
    named beside them, two records are indistinguishable, so a leaking factory
    and a clean one average into a reading about neither; and a reader cannot
    tell which host a reclaim gave its envelope back to.

    The factories sharing that daemon are named too, because the daemon is
    what a sweep is addressed to while a factory is what an operator
    configures, and only the second is a name they can act on.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)
    journal = _Journal()

    _ = pass_container_sweeps(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=journal),
        factories=(_HP,),
        run_statuses=_STATUSES,
        dry_run=False,
    )

    summary = _record(records=journal.written, stage=_SWEEP_STAGE)
    assert summary.get("docker_host") == _DOCKER_HOST
    assert summary.get("factory_names") == [_HP.name]


def test_every_per_container_record_names_the_daemon_it_was_read_from(
    tmp_path: Path,
) -> None:
    """A container name is unique to its daemon only by convention, not by fact.

    Two factory hosts can each run a `fabro-run-<id>` container for the same
    run id — a re-dispatch of one work-item is a routine way to get one — so a
    reclaim or a hold that named only the container would be a record nobody
    can place. Each is stamped with the daemon its reading came from.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)
    journal = _Journal()

    _ = pass_container_sweeps(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=journal),
        factories=(_HP,),
        run_statuses=_STATUSES,
        dry_run=False,
    )

    assert [(record["stage"], record.get("docker_host")) for record in journal.written] == [
        (_RECLAIMED_STAGE, _DOCKER_HOST),
        (_HELD_STAGE, _DOCKER_HOST),
        (_SWEEP_STAGE, _DOCKER_HOST),
    ]


def test_a_refused_removal_is_counted_as_refused_and_not_as_reclaimed(tmp_path: Path) -> None:
    """A daemon that would not remove the container gave no envelope back.

    So the reclaimed byte total stays at zero while the container is still
    named — the record says a removal was attempted and refused, which is a
    different thing to report than a reclaim.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT, rm_exit_code=1)

    records = _journalled(runner=runner, tmp_path=tmp_path, status_by_run=_STATUSES)

    reclaimed = _record(records=records, stage=_RECLAIMED_STAGE)
    assert reclaimed["removed"] is False
    assert "1" in str(reclaimed["detail"])
    summary = _record(records=records, stage=_SWEEP_STAGE)
    assert (summary["containers_removed"], summary["containers_remove_failed"]) == (0, 1)
    assert summary["memory_limit_bytes_reclaimed"] == 0


def test_an_unmeasured_limit_is_counted_rather_than_summed_as_zero(tmp_path: Path) -> None:
    """A limit nobody could read must not silently shrink the reclaimed total.

    The byte sum would read as a complete measurement while omitting a
    container, so the count of unmeasured limits travels beside it.
    """
    runner = _Docker(
        ps_stdout=f"fabro-run-{_TERMINAL_RUN}\n",
        inspect_stdout=f"/fabro-run-{_TERMINAL_RUN}\t<no value>\n",
    )

    records = _journalled(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run={_TERMINAL_RUN: "succeeded"},
    )

    assert _record(records=records, stage=_RECLAIMED_STAGE)["memory_limit_bytes"] is None
    summary = _record(records=records, stage=_SWEEP_STAGE)
    assert summary["memory_limit_bytes_reclaimed"] == 0
    assert summary["reclaimed_limits_unmeasured"] == 1


def test_an_unobservable_inventory_still_leaves_a_record_saying_so(tmp_path: Path) -> None:
    """The record that makes a BLINDED sweep tell itself apart from a clean host.

    Both leave zero per-container records, so without `inventory_observed`
    plus the detail, a daemon that refused the listing reads exactly like a
    host with nothing leaked on it.
    """
    runner = _Docker(ps_exit_code=127)

    records = _journalled(runner=runner, tmp_path=tmp_path, status_by_run=_STATUSES)

    assert [record["stage"] for record in records] == [_SWEEP_STAGE]
    summary = records[0]
    assert summary["inventory_observed"] is False
    assert summary["containers_observed"] == 0
    assert "127" in str(summary["detail"])


def test_a_dry_run_writes_nothing_to_the_journal(tmp_path: Path) -> None:
    """A projection records nothing, because nothing happened to record."""
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)

    records = _journalled(
        runner=runner,
        tmp_path=tmp_path,
        status_by_run=_STATUSES,
        dry_run=True,
    )

    assert records == []


def test_the_pass_level_sweep_records_through_the_passes_own_journal(tmp_path: Path) -> None:
    """The wiring: the reconciliation pass's own composer does the recording.

    Asserted at `pass_container_sweeps` rather than at the journal function,
    because a record-shaped function nobody calls passes every test above
    while journaling nothing in production.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)
    journal = _Journal()

    sweeps = pass_container_sweeps(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=journal),
        factories=(_HP,),
        run_statuses=_STATUSES,
        dry_run=False,
    )

    assert [run.run_id for sweep in sweeps for run in sweep.reclaimed] == [_TERMINAL_RUN]
    assert [record["stage"] for record in journal.written] == [
        _RECLAIMED_STAGE,
        _HELD_STAGE,
        _SWEEP_STAGE,
    ]


def test_a_pass_that_surveyed_nothing_neither_sweeps_nor_records(tmp_path: Path) -> None:
    """No inventory to grade against: no daemon call and no record at all.

    The empty tuple of sweeps is what says so. A single sweep value reporting
    zero containers would be the claim this pass is least entitled to make.
    """
    runner = _Docker(ps_stdout=_PS_STDOUT, inspect_stdout=_INSPECT_STDOUT)
    journal = _Journal()

    sweeps = pass_container_sweeps(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=journal),
        factories=(),
        run_statuses={},
        dry_run=False,
    )

    assert runner.calls == []
    assert journal.written == []
    assert sweeps == ()
