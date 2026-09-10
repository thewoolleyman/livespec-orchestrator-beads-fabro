"""Scenarios 104, 105 and 106 — reconciliation releases the runs the ledger disowns.

Integration-tier binding for three `SPECIFICATION/scenarios.md` headings:

- `## Scenario 104 — An item closed by any route releases its non-terminal run`
- `## Scenario 105 — A parked run past its grace period is exported and
  abandoned, and its item is untouched`
- `## Scenario 106 — Reconciliation addresses every declared factory by its
  server target`

Everything below the factory boundary is production code, driven end to end
through `reconcile_runs` and folded through `reconcile_pass_summary`. The
work-items are seeded, closed, and read back through the REAL store seam
against the in-memory `FakeBeadsClient`; the preserve-by-reference export
writes and reads back a REAL ledger comment through that same client; and the
journal is a real append-only `JournalFile` on disk whose lines are re-read as
JSON. No private helper of the reconciler is poked directly.

Only the two seams that leave the process are stood in: the `fabro` CLI and
the factory's HTTP face. The HTTP stand-in is what makes the
export-before-terminate ordering CHECKABLE rather than assumed — it snapshots
the item's ledger comments at the instant each route is contacted, so "the
export had already landed" is an observation about the FIRST termination call
rather than about the end state, which a terminate-then-export order would
satisfy just as well.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    PRESERVE_POINTER_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs import reconcile_runs
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    read_journaled_runs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_pass import (
    reconcile_pass_summary,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands.close_work_item import close_completed
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ID_PREFIX = "bd-ib"
_TENANT = "livespec-orchestrator-beads-fabro"
_GRACE_SECONDS = 1800

_HP_SERVER = "https://hp.example:32276"
_VPS_SERVER = "https://vps.example:32276"
_HP_DEV_TOKEN_VALUE = "hp-fixture-dev-token"
_VPS_DEV_TOKEN_VALUE = "vps-fixture-dev-token"
# Both factories resolve a bearer credential, so no pass degrades onto the
# unauthenticated `fabro rm -f` fallback and the termination routes under test
# are the ones the scenarios name.
_HP = FactoryTarget(name="hp", server=_HP_SERVER, dev_token=_HP_DEV_TOKEN_VALUE)
_VPS = FactoryTarget(name="vps", server=_VPS_SERVER, dev_token=_VPS_DEV_TOKEN_VALUE)

# What the factory answers on `GET /questions` for a run parked at the
# in-loop gate: the graph's own Abandon edge, carrying the wire `key` the
# typed answer request selects by.
_QUESTIONS_BODY = json.dumps(
    {
        "data": [
            {
                "id": "q-1",
                "options": [{"key": "A", "label": "[A] Abandon (leave open for triage)"}],
            }
        ],
        "meta": {"has_more": False},
    }
)


@dataclass(kw_only=True)
class _FabroCli:
    """The factory-side `fabro` CLI, keyed by the server each argv names."""

    ps_by_server: dict[str, str] = field(default_factory=dict)
    inspect_by_run: dict[str, str] = field(default_factory=dict)
    unreachable_servers: frozenset[str] = frozenset()
    ps_servers: list[str] = field(default_factory=list)
    verbs: list[str] = field(default_factory=list)

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
        server = argv[argv.index("--server") + 1]
        self.verbs.append(argv[1])
        if argv[1] == "ps":
            self.ps_servers.append(server)
            if server in self.unreachable_servers:
                return CommandResult(exit_code=7, stdout="", stderr="connection refused")
            return CommandResult(exit_code=0, stdout=self.ps_by_server.get(server, "[]"), stderr="")
        if argv[1] == "inspect":
            return CommandResult(
                exit_code=0, stdout=self.inspect_by_run.get(argv[2], "[]"), stderr=""
            )
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _FactoryHttp:
    """The factory's HTTP face, recording what the LEDGER held at each call.

    `ledger_at_call` is the load-bearing part. Asserting that a pointer comment
    exists after the pass proves only that both things happened; snapshotting
    the item's comments as each termination route is contacted is what proves
    the export came FIRST.
    """

    item_ids: tuple[str, ...]
    calls: list[str] = field(default_factory=list)
    ledger_at_call: list[tuple[str, ...]] = field(default_factory=list)

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
        self.ledger_at_call.append(_comment_texts(item_ids=self.item_ids))
        answered = _QUESTIONS_BODY if url.endswith("/questions") else "{}"
        return FabroHttpResult(
            status=200,
            body=answered,
            error=None,
            payload=None,
            succeeded=True,
        )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Drive the store onto the in-memory tenant, isolated per test."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


# --------------------------------------------------------------------------
# Scenario 104 — an item that left `active` releases its non-terminal run.
# --------------------------------------------------------------------------


def test_scenario104_an_item_that_left_active_releases_its_run(tmp_path: Path) -> None:
    """Given a non-terminal run attributed to an item hand-closed with no Dispatcher alive,
    When reconciliation runs,
    Then the run's record is exported and read back BEFORE it is terminated,
    And one record naming the orphan reason is journaled,
    And the item's status, blocked_reason and labels are unchanged."""
    _seed(item_id="bd-ib-departed", status="active")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-departed", run_id="01DEPARTED")
    _ = close_completed(path=_config(), item_id="bd-ib-departed", reason="hand-implemented")
    before = _item_state(item_id="bd-ib-departed")
    runner = _FabroCli(
        ps_by_server={
            _HP_SERVER: _ps(_run(run_id="01DEPARTED", kind="running", item_suffix="departed"))
        }
    )
    http = _FactoryHttp(item_ids=("bd-ib-departed",))

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, journal=journal, runner=runner, http=http),
        factories=[_HP],
    )

    assert [
        (run.run_id, run.orphan_reason, run.termination_route) for run in summary.reconciled
    ] == [("01DEPARTED", "item-not-active", "cancel")]
    # The export ran before anything reached the factory's termination routes:
    # at the instant the FIRST route was contacted the pointer was already
    # readable back off the item.
    assert runner.verbs == ["ps", "dump"]
    assert http.calls[0] == f"POST {_HP_SERVER}/api/v1/runs/01DEPARTED/cancel"
    assert _pointer_present(texts=http.ledger_at_call[0], run_id="01DEPARTED")
    reconciled = _records(journal=journal)[-1]
    assert reconciled["stage"] == "orphan-run-reconciled"
    assert reconciled["orphan_reason"] == "item-not-active"
    assert reconciled["export_comment_id"] is not None
    assert _item_state(item_id="bd-ib-departed") == before


def test_scenario104_a_live_run_under_a_matching_claim_is_left_alone(tmp_path: Path) -> None:
    """A running run whose item is `active` and whose journaled run id IS that run
    is not an orphan, even though no Dispatcher process is watching it."""
    _seed(item_id="bd-ib-claimed", status="active")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-claimed", run_id="01CLAIMED")
    seeded = _records(journal=journal)
    runner = _FabroCli(
        ps_by_server={
            _HP_SERVER: _ps(_run(run_id="01CLAIMED", kind="running", item_suffix="claimed"))
        }
    )
    http = _FactoryHttp(item_ids=("bd-ib-claimed",))

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, journal=journal, runner=runner, http=http),
        factories=[_HP],
    )

    assert (summary.reconciled, summary.errors, summary.held) == ((), (), ())
    assert http.calls == []
    assert runner.verbs == ["ps"]
    assert _records(journal=journal) == seeded


def test_scenario104_a_superseded_run_is_released_and_the_newest_is_left_alone(
    tmp_path: Path,
) -> None:
    """Two non-terminal runs on one active item: the ledger's newest journaled run
    id names the second, so the FIRST is reconciled as `superseded-run` and the
    second is left running."""
    _seed(item_id="bd-ib-super", status="active")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-super", run_id="01FIRST")
    _journal_dispatch(journal=journal, item_id="bd-ib-super", run_id="01SECOND")
    before = _item_state(item_id="bd-ib-super")
    runner = _FabroCli(
        ps_by_server={
            _HP_SERVER: _ps(
                _run(run_id="01FIRST", kind="running", item_suffix="super"),
                _run(run_id="01SECOND", kind="running", item_suffix="super"),
            )
        }
    )
    http = _FactoryHttp(item_ids=("bd-ib-super",))

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, journal=journal, runner=runner, http=http),
        factories=[_HP],
    )

    assert [(run.run_id, run.orphan_reason) for run in summary.reconciled] == [
        ("01FIRST", "superseded-run")
    ]
    assert http.calls == [f"POST {_HP_SERVER}/api/v1/runs/01FIRST/cancel"]
    assert _item_state(item_id="bd-ib-super") == before


# --------------------------------------------------------------------------
# Scenario 105 — a parked run past its grace is exported and abandoned.
# --------------------------------------------------------------------------


def test_scenario105_a_park_past_grace_is_abandoned_and_the_item_is_untouched(
    tmp_path: Path,
) -> None:
    """Given a run parked at a human gate for longer than the configured grace,
    And a work-item still LIVE at `blocked / needs-human`,
    When reconciliation runs,
    Then the export is read back before the run is touched,
    And the run is ended through the interview's own Abandon answer route,
    And the record carries the measured park beside the bound it passed,
    And the item's status, blocked_reason and labels are unchanged."""
    _seed(item_id="bd-ib-parked", status="blocked", blocked_reason="needs-human")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-parked", run_id="01PARKED")
    before = _item_state(item_id="bd-ib-parked")
    runner = _FabroCli(
        ps_by_server={
            _HP_SERVER: _ps(_run(run_id="01PARKED", kind="blocked", item_suffix="parked"))
        },
        inspect_by_run={"01PARKED": json.dumps([{"status": {"kind": "blocked"}, "blocked_at": 0}])},
    )
    http = _FactoryHttp(item_ids=("bd-ib-parked",))

    summary = reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            journal=journal,
            runner=runner,
            http=http,
            now_epoch=float(_GRACE_SECONDS + 1),
        ),
        factories=[_HP],
    )

    assert [
        (run.run_id, run.orphan_reason, run.termination_route) for run in summary.reconciled
    ] == [("01PARKED", "blocked-past-grace", "questions-answer")]
    assert summary.held == ()
    # The Abandon ANSWER route, not cancel and not `fabro rm -f`.
    assert http.calls == [
        f"GET {_HP_SERVER}/api/v1/runs/01PARKED/questions",
        f"POST {_HP_SERVER}/api/v1/runs/01PARKED/questions/q-1/answer",
    ]
    assert _pointer_present(texts=http.ledger_at_call[0], run_id="01PARKED")
    reconciled = _records(journal=journal)[-1]
    assert reconciled["stage"] == "orphan-run-reconciled"
    assert (reconciled["parked_seconds"], reconciled["grace_seconds"]) == (1801.0, _GRACE_SECONDS)
    assert _item_state(item_id="bd-ib-parked") == before


def test_scenario105_a_park_inside_grace_is_held_with_seconds_remaining(tmp_path: Path) -> None:
    """A park shorter than the grace is REPORTED as held, with the time it has
    left, and nothing is exported, answered, cancelled or removed."""
    _seed(item_id="bd-ib-young", status="blocked", blocked_reason="needs-human")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-young", run_id="01YOUNG")
    seeded = _records(journal=journal)
    runner = _FabroCli(
        ps_by_server={_HP_SERVER: _ps(_run(run_id="01YOUNG", kind="blocked", item_suffix="young"))},
        inspect_by_run={"01YOUNG": json.dumps([{"blocked_at": "1970-01-01T00:00:00Z"}])},
    )
    http = _FactoryHttp(item_ids=("bd-ib-young",))

    summary = reconcile_runs(
        inputs=_inputs(
            tmp_path=tmp_path,
            journal=journal,
            runner=runner,
            http=http,
            now_epoch=300.0,
        ),
        factories=[_HP],
    )

    assert summary.reconciled == ()
    assert [(run.run_id, run.hold_reason, run.seconds_remaining) for run in summary.held] == [
        ("01YOUNG", "blocked-within-grace", 1500.0)
    ]
    assert http.calls == []
    assert runner.verbs == ["ps", "inspect"]
    assert _records(journal=journal) == seeded
    assert _comment_texts(item_ids=("bd-ib-young",)) == ()


# --------------------------------------------------------------------------
# Scenario 106 — every declared factory is addressed by its own server target.
# --------------------------------------------------------------------------


def test_scenario106_each_declared_factory_is_queried_by_its_own_server_target(
    tmp_path: Path,
) -> None:
    """Given two declared factories, one of them unreachable,
    When reconciliation runs,
    Then each is queried by ITS OWN declared server target,
    And the unreachable one produces a journaled reconciliation error,
    And reconciliation of the reachable one completes."""
    _seed(item_id="bd-ib-remote", status="active")
    journal = _journal(tmp_path=tmp_path)
    _journal_dispatch(journal=journal, item_id="bd-ib-remote", run_id="01REMOTE")
    _ = close_completed(path=_config(), item_id="bd-ib-remote", reason="hand-implemented")
    runner = _FabroCli(
        ps_by_server={
            _VPS_SERVER: _ps(_run(run_id="01REMOTE", kind="running", item_suffix="remote"))
        },
        unreachable_servers=frozenset({_HP_SERVER}),
    )
    http = _FactoryHttp(item_ids=("bd-ib-remote",))

    summary = reconcile_runs(
        inputs=_inputs(tmp_path=tmp_path, journal=journal, runner=runner, http=http),
        factories=[_HP, _VPS],
    )

    # Each factory was surveyed at the url IT declares — not once at a default
    # pool, and never one factory's inventory read through the other's target.
    assert runner.ps_servers == [_HP_SERVER, _VPS_SERVER]
    assert [
        (error.factory_name, error.factory_server_url, error.reason) for error in summary.errors
    ] == [("hp", _HP_SERVER, "factory-ps-failed")]
    assert [(run.factory_name, run.factory_server_url) for run in summary.reconciled] == [
        ("vps", _VPS_SERVER)
    ]
    stages = [record["stage"] for record in _records(journal=journal)]
    assert stages[-2:] == ["orphan-run-reconciled", "orphan-run-reconcile-error"]
    pass_summary = reconcile_pass_summary(factories=[_HP, _VPS], summary=summary)
    assert pass_summary.factory_names == ("hp", "vps")
    assert (pass_summary.factories_surveyed, pass_summary.errors) == (2, 1)
    assert (pass_summary.orphans_found, pass_summary.orphans_reconciled) == (1, 1)


# --------------------------------------------------------------------------
# Fixtures — the real store, the real journal, the stood-in factory boundary.
# --------------------------------------------------------------------------


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix=_ID_PREFIX,
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _seed(*, item_id: str, status: str, blocked_reason: str | None = None) -> None:
    """Write one work-item through the REAL store seam onto the in-memory tenant."""
    append_work_item(
        path=_config(),
        item=WorkItem(
            id=item_id,
            type="task",
            status=status,
            blocked_reason=blocked_reason,
            title=item_id,
            description=item_id,
            origin="freeform",
            gap_id=None,
            rank="a0",
            assignee=None,
            depends_on=(),
            captured_at="2026-08-30T00:00:00Z",
            resolution=None,
            reason=None,
            audit=None,
            superseded_by=None,
        ),
    )


def _item_state(*, item_id: str) -> tuple[str, str | None, tuple[str, ...]]:
    """The trio reconciliation may never touch: status, blocked_reason, labels."""
    item = {row.id: row for row in read_work_items(path=_config())}[item_id]
    record = make_beads_client(config=_config()).show_issue(issue_id=item_id)
    return (item.status, item.blocked_reason, tuple(sorted(record.get("labels", []))))


def _comment_texts(*, item_ids: tuple[str, ...]) -> tuple[str, ...]:
    ledger = make_beads_client(config=_config())
    return tuple(
        str(comment["text"])
        for item_id in item_ids
        for comment in ledger.list_comments(issue_id=item_id)
    )


def _pointer_present(*, texts: tuple[str, ...], run_id: str) -> bool:
    return any(PRESERVE_POINTER_MARKER in text and run_id in text for text in texts)


def _journal(*, tmp_path: Path) -> JournalFile:
    return JournalFile(path=tmp_path / "dispatch-journal.jsonl")


def _journal_dispatch(*, journal: JournalFile, item_id: str, run_id: str) -> None:
    journal.append(
        record={
            "stage": "dispatch-run-stamp",
            "work_item_id": item_id,
            "fabro_run_id": run_id,
        }
    )


def _records(*, journal: JournalFile) -> list[dict[str, Any]]:
    lines = journal.path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _inputs(
    *,
    tmp_path: Path,
    journal: JournalFile,
    runner: _FabroCli,
    http: _FactoryHttp,
    now_epoch: float | None = None,
) -> ReconcileInputs:
    return ReconcileInputs(
        repo=tmp_path,
        fabro_bin="fabro",
        id_prefix=_ID_PREFIX,
        items=list(read_work_items(path=_config())),
        journaled=read_journaled_runs(path=journal.path),
        runner=runner,
        journal=journal,
        ledger=make_beads_client(config=_config()),
        http=http,
        blocked_run_grace_seconds=_GRACE_SECONDS,
        now_epoch=now_epoch,
    )


def _ps(*runs: dict[str, Any]) -> str:
    return json.dumps(list(runs))


def _run(*, run_id: str, kind: str, item_suffix: str) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "goal": f"Work-item: {_ID_PREFIX}-{item_suffix}\nRepo: /tmp/repo",
        "status": {"kind": kind},
    }
