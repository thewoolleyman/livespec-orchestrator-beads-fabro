"""Tests that the reconciliation pass itself reclaims a terminal run's container.

The sweep is wired INTO `reconcile_runs` rather than offered as a separate
command, which is what makes the acceptance assertion hold for every route
that reconciles: the `reconcile-runs` subcommand the host timer invokes, the
loop tick, and the lifecycle hook that fires the moment a work-item leaves
`active`. A sweep reachable only from its own entry point would have to be
remembered by each of them.

It rides THIS pass's own `fabro ps` inventory rather than taking a second
one. That is not a saving: the two readings would be taken a moment apart,
and a run that terminated in between would be read as live by one and
terminal by the other with nothing in either output to say which reading the
sweep acted on.

A FAILED run is the case the whole item was filed from, and it is the case a
test over the ORPHAN lane cannot reach: the orphan join considers only
non-terminal runs, so a failed run is not an orphan, nothing about it is
reconciled, and before this wiring its container was simply never looked at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import reconcile_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_container_port import DOCKER_BIN
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_HP_DEV_TOKEN_VALUE = "hp-fixture-dev-token"
# hp also declares the Docker daemon running ITS sandbox containers, which is
# the daemon this lane addresses. A factory declaring none is reported rather
# than swept through the reconciling host's own daemon.
_HP_DOCKER_HOST = "ssh://cwoolley@hp.example"
_HP = FactoryTarget(
    name="hp",
    server="https://hp.example:32276",
    dev_token=_HP_DEV_TOKEN_VALUE,
    docker_host=_HP_DOCKER_HOST,
)
# The two runs the hp storage session measured on 2026-10-13: a `failed` run
# whose container was still running, and the item's live replacement.
_FAILED_RUN = "01M4RM5YPANB7A4900404SEZXY"
_LIVE_RUN = "01M4SK59TGF6Q0CX3A1FV0Q5QE"
_ORPHAN_RUN = "01M4S5MKW3JHX4T8VB8ZMJE9VV"
_LIMIT = 4294967296


# Every stage the container lane of a reconciliation pass writes shares this
# prefix. Spelled out rather than imported so this file keeps naming the
# records it means to separate.
_SWEEP_STAGE_PREFIX = "sandbox-container-"


@dataclass(kw_only=True)
class _Runner:
    """One fake CLI for BOTH binaries, keyed on argv[0] before the verb.

    Keying on the verb alone would be wrong in the one way that matters here:
    `fabro ps` and `docker ps` are both `ps`, so a fake that read argv[1]
    first would answer the factory inventory to the container listing and the
    sweep would grade a run payload as a container name.
    """

    fabro_ps_json: str = "[]"
    docker_ps_stdout: str = ""
    docker_inspect_stdout: str = ""
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
        if argv[0] == DOCKER_BIN:
            return self._docker(argv=argv)
        if argv[1] == "ps":
            return CommandResult(exit_code=0, stdout=self.fabro_ps_json, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")

    def _docker(self, *, argv: list[str]) -> CommandResult:
        # Membership rather than a fixed index: every docker argv opens with
        # the global `--host <daemon>` pair naming the factory host's daemon,
        # so an index-keyed fake would read that address as the verb.
        if "inspect" in argv:
            return CommandResult(exit_code=0, stdout=self.docker_inspect_stdout, stderr="")
        if "ps" in argv:
            return CommandResult(exit_code=0, stdout=self.docker_ps_stdout, stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    """Answers every route 200 with an empty body, recording each one.

    An empty questions payload carries no abandonable option, so an orphan
    takes the cancel route — which is all this file needs from the run lane,
    and keeps the interview shapes where they are already asserted.
    """

    calls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (headers, body, timeout_seconds)
        self.calls.append(f"{method} {url}")
        return FabroHttpResult(status=200, body="{}", error=None, payload=None, succeeded=True)


@dataclass(kw_only=True)
class _Journal:
    """Records the RUN lane in `written` and the CONTAINER lane in `swept`.

    The same pass sweeps this host's sandbox containers and journals what it
    swept, so one journal now carries two lanes. Splitting them in the fake is
    what keeps every position-based assertion in this file — a `[-1]`, an
    exact stage list, an empty-journal claim — about the lane it names.
    """

    written: list[dict[str, object]] = field(default_factory=list)
    swept: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        if str(record["stage"]).startswith(_SWEEP_STAGE_PREFIX):
            self.swept.append(record)
            return
        self.written.append(record)


@dataclass(kw_only=True)
class _Ledger:
    """The comments-only seam, recording its verbs so "no write" is a finding."""

    comments: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    verbs: list[str] = field(default_factory=list)

    def list_comments(self, *, issue_id: str) -> list[dict[str, Any]]:
        self.verbs.append(f"list_comments:{issue_id}")
        return list(self.comments.get(issue_id, []))

    def add_comment(self, *, issue_id: str, body: str) -> None:
        self.verbs.append(f"add_comment:{issue_id}")
        self.comments.setdefault(issue_id, []).append({"id": f"c-{issue_id}", "text": body})


def _docker_calls(*, runner: _Runner) -> list[list[str]]:
    return [argv for argv in runner.calls if argv[0] == DOCKER_BIN]


def _removed(*, runner: _Runner) -> list[str]:
    return [argv[-1] for argv in _docker_calls(runner=runner) if "rm" in argv]


def _only_sweep(*, summary: Any) -> Any:
    """The pass's single sweep, with the one-per-daemon shape asserted.

    One surveyed factory declaring one daemon owes exactly one sweep. Reading
    `[0]` without the count would let a pass that swept the same daemon twice
    satisfy every assertion below while removing containers it had already
    graded.
    """
    assert len(summary.containers) == 1, f"expected one sweep, got {len(summary.containers)}"
    return summary.containers[0]


def _runner() -> _Runner:
    return _Runner(
        fabro_ps_json=json.dumps(
            [
                _run_record(run_id=_FAILED_RUN, kind="failed", work_item_id="bd-ib-failed"),
                _run_record(run_id=_LIVE_RUN, kind="running", work_item_id="bd-ib-live"),
            ]
        ),
        docker_ps_stdout=f"fabro-run-{_FAILED_RUN}\nfabro-run-{_LIVE_RUN}\n",
        docker_inspect_stdout=(
            f"/fabro-run-{_FAILED_RUN}\t{_LIMIT}\n/fabro-run-{_LIVE_RUN}\t{_LIMIT}\n"
        ),
    )


def _run_record(*, run_id: str, kind: str, work_item_id: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "goal": f"Work-item: {work_item_id}\nRepo: /tmp/repo",
        "status": {"kind": kind},
    }


def _inputs(
    *,
    tmp_path: Path,
    runner: _Runner,
    journal: _Journal,
    stamps: tuple[tuple[str, str], ...] = (
        (_FAILED_RUN, "bd-ib-failed"),
        (_LIVE_RUN, "bd-ib-live"),
    ),
    items: tuple[WorkItem, ...] = (),
    ledger: _Ledger | None = None,
    transport: _Transport | None = None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix="bd-ib",
        items=items
        or (
            _item(id="bd-ib-failed", status="active"),
            _item(id="bd-ib-live", status="active"),
        ),
        journaled=journaled_runs(
            text="\n".join(
                json.dumps({"stage": "dispatch-run-stamp", "run_id": run_id, "work_item_id": item})
                for run_id, item in stamps
            )
        ),
        runner=runner,
        journal=journal,
        ledger=_Ledger() if ledger is None else ledger,
        http=_Transport() if transport is None else transport,
    )


def _item(*, id: str, status: str) -> WorkItem:
    return WorkItem(
        id=id,
        type="task",
        status=status,
        blocked_reason=None,
        title=id,
        description=id,
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-13T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def test_reconciling_a_factory_removes_the_container_of_its_failed_run(tmp_path: Path) -> None:
    """The acceptance assertion: a failed run's sandbox container is reclaimed.

    Both work-items are `active` and both runs are journaled, so neither run
    is an orphan and the orphan lane reconciles nothing. The container is
    nonetheless gone, which is the whole point: the run lane had already
    finished with this run and the envelope was still being spent.
    """
    runner = _runner()

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=_Journal()),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert _removed(runner=runner) == [f"fabro-run-{_FAILED_RUN}"]
    assert [
        (run.run_id, run.run_status_kind, run.memory_limit_bytes, run.removed)
        for run in _only_sweep(summary=summary).reclaimed
    ] == [(_FAILED_RUN, "failed", _LIMIT, True)]
    assert [(run.run_id, run.hold_reason) for run in _only_sweep(summary=summary).held] == [
        (_LIVE_RUN, "run-live")
    ]
    assert _only_sweep(summary=summary).observed is True


def test_a_dry_run_projects_the_reclaim_without_removing_anything(tmp_path: Path) -> None:
    """A dry run is a projection, so it may read the daemon and never write it."""
    runner = _runner()

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=_Journal()),
        factories=[_HP],
        dry_run=True,
    )

    assert _removed(runner=runner) == []
    assert [(run.run_id, run.removed) for run in _only_sweep(summary=summary).reclaimed] == [
        (_FAILED_RUN, False)
    ]
    assert _only_sweep(summary=summary).dry_run is True


def test_a_factory_that_could_not_be_surveyed_leaves_every_container_standing(
    tmp_path: Path,
) -> None:
    """The fail-closed join: no inventory to grade against means no removal.

    A `fabro ps` whose payload does not parse contributes no run statuses, so
    every container on the host reads as a run no surveyed server reported.
    That is the one reading under which a sweep must do nothing, and it is
    reached here through the factory rather than through the daemon.
    """
    runner = _runner()
    runner.fabro_ps_json = ""

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, runner=runner, journal=_Journal()),
        factories=[_HP],
    )

    assert _removed(runner=runner) == []
    assert [(run.run_id, run.hold_reason) for run in _only_sweep(summary=summary).held] == [
        (_FAILED_RUN, "run-unobserved"),
        (_LIVE_RUN, "run-unobserved"),
    ]


def test_the_run_lane_and_the_container_lane_both_act_in_one_pass(tmp_path: Path) -> None:
    """Two lanes, one pass — and the ordering consequence worth knowing about.

    The orphan lane releases the blocked run whose item is closed, and the
    container lane removes the failed run's container, in the same pass.

    The orphan's OWN container is HELD, and that is correct rather than a
    miss: the sweep grades against the inventory this pass already read,
    taken before the termination, so at the moment of the reading that run was
    genuinely live. A sweep that removed it would be acting on a status it had
    not observed. The next pass reads it as terminal and reclaims it, which is
    why the hold is reported rather than silently skipped.
    """
    runner = _Runner(
        fabro_ps_json=json.dumps(
            [
                _run_record(run_id=_FAILED_RUN, kind="failed", work_item_id="bd-ib-failed"),
                _run_record(run_id=_ORPHAN_RUN, kind="blocked", work_item_id="bd-ib-orphan"),
            ]
        ),
        docker_ps_stdout=f"fabro-run-{_FAILED_RUN}\nfabro-run-{_ORPHAN_RUN}\n",
        docker_inspect_stdout=(
            f"/fabro-run-{_FAILED_RUN}\t{_LIMIT}\n/fabro-run-{_ORPHAN_RUN}\t{_LIMIT}\n"
        ),
    )
    journal = _Journal()
    ledger = _Ledger()
    transport = _Transport()

    summary = reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            runner=runner,
            journal=journal,
            ledger=ledger,
            transport=transport,
            stamps=((_FAILED_RUN, "bd-ib-failed"), (_ORPHAN_RUN, "bd-ib-orphan")),
            items=(
                _item(id="bd-ib-failed", status="active"),
                _item(id="bd-ib-orphan", status="closed"),
            ),
        ),
        factories=[_HP],
    )

    assert [
        (run.run_id, run.orphan_reason, run.termination_route) for run in summary.reconciled
    ] == [(_ORPHAN_RUN, "item-not-active", "cancel")]
    # Read, write, then read BACK: the export verifies its own pointer comment
    # before the termination is allowed to proceed.
    assert ledger.verbs == [
        "list_comments:bd-ib-orphan",
        "add_comment:bd-ib-orphan",
        "list_comments:bd-ib-orphan",
    ]
    assert transport.calls[-1].endswith(f"/runs/{_ORPHAN_RUN}/cancel")
    assert [record["stage"] for record in journal.written] == ["orphan-run-reconciled"]
    assert _removed(runner=runner) == [f"fabro-run-{_FAILED_RUN}"]
    # Both lanes journaled, through the one journal the pass was handed.
    assert [record["stage"] for record in journal.swept] == [
        "sandbox-container-reclaimed",
        "sandbox-container-held",
        "sandbox-container-sweep",
    ]
    assert [(run.run_id, run.hold_reason) for run in _only_sweep(summary=summary).held] == [
        (_ORPHAN_RUN, "run-live")
    ]
