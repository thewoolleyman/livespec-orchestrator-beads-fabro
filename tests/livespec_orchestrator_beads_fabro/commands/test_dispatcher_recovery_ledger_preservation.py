"""Recovery routes use the ledger claim before deciding preserved work is gone."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimStamp, record_claim_stamp
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_admission as _admission,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_recovery_routing as routing,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_preserved import (
    NEEDS_HUMAN_REF_PREFIX,
    PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    PRESERVED_SOURCE_PUBLISHED_HEAD,
    PRESERVED_SOURCE_TERMINAL_TREE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    ROUTE_FRESH,
    ROUTE_HELD,
    ROUTE_SEEDED,
)
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

from tests.livespec_orchestrator_beads_fabro.commands._recovery_tip_reads import tip_read_answer

_ = _admission

_ITEM_ID = "bd-ib-oknwxm"
_RUN = "01M6SC2RDJ7F0000000000000Z"
_DISPATCH = "b0f24e0d8a654fb4b9bf4692af0a80d5"
_TREE = "6e0312b1a" * 5
_TENANT = "livespec-orch-beads-fabro"


class _Runner:
    """Scripted origin responses, with an empty successful listing as the control."""

    answers: ClassVar[dict[str, CommandResult]] = {}
    calls: ClassVar[list[list[str]]] = []

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
        _Runner.calls.append(argv)
        joined = " ".join(argv)
        for needle, answer in _Runner.answers.items():
            if needle in joined:
                return answer
        if (tip := tip_read_answer(argv=argv)) is not None:
            return tip
        return CommandResult(exit_code=0, stdout="", stderr="")


@pytest.fixture(autouse=True)
def _fresh_fake_ledger(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _item() -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="bug",
        status="ready",
        title="A released item whose earlier run is known only to the ledger",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _config(*, repo: Path) -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix="bd-ib",
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _write_config(*, repo: Path) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib"},
                }
            }
        ),
        encoding="utf-8",
    )


def _claim(*, repo: Path) -> None:
    _write_config(repo=repo)
    config = _config(repo=repo)
    append_work_item(path=config, item=_item())
    record_claim_stamp(
        path=config,
        work_item_id=_ITEM_ID,
        stamp=ClaimStamp(
            dispatch_id=_DISPATCH,
            dispatching_host="other-host",
            run_id=_RUN,
            factory_name="petri",
            factory_server=None,
        ),
    )


def _journal(*, repo: Path, records: Sequence[dict[str, object]]) -> JournalFile:
    path = repo / "journal.jsonl"
    _ = path.write_text("".join(f"{json.dumps(one)}\n" for one in records), encoding="utf-8")
    return JournalFile(path=path)


def _route(
    *,
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    records: Sequence[dict[str, object]],
    answers: dict[str, CommandResult] | None = None,
) -> tuple[routing.RecoveryRouting, JournalFile]:
    journal = _journal(repo=repo, records=records)
    _Runner.answers = (
        {"gh pr list": CommandResult(exit_code=0, stdout="[]", stderr="")}
        if answers is None
        else answers
    )
    _Runner.calls = []
    monkeypatch.setattr(ShellCommandRunner, "run", _Runner.run)
    return (
        routing.route_recovery(
            args=argparse.Namespace(
                repo=str(repo),
                journal=str(journal.path),
                workflow_name="implement-work-item",
                fabro_bin="fabro",
            ),
            repo=repo,
            candidates=[_item()],
            journal=journal,
        ),
        journal,
    )


def _released() -> tuple[dict[str, object], ...]:
    return ({"stage": "provider-limit-release", "work_item_id": _ITEM_ID},)


def test_a_ledger_run_id_finds_its_needs_human_tree_before_fresh_reclaim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claim(repo=tmp_path)
    terminal_ref = f"{NEEDS_HUMAN_REF_PREFIX}/{_RUN}"
    routed, _ = _route(
        repo=tmp_path,
        monkeypatch=monkeypatch,
        records=_released(),
        answers={
            "gh pr list": CommandResult(exit_code=0, stdout="[]", stderr=""),
            f"{NEEDS_HUMAN_REF_PREFIX}/*": CommandResult(
                exit_code=0, stdout=f"{_TREE}\t{terminal_ref}\n", stderr=""
            ),
        },
    )

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == ROUTE_SEEDED
    assert route.seed is not None
    assert route.seed.source_run_id == _RUN
    assert route.seed.preservation_ref == terminal_ref


def test_an_item_with_no_recoverable_run_id_is_held_without_reclaim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    routed, journal = _route(repo=tmp_path, monkeypatch=monkeypatch, records=_released())

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == ROUTE_HELD
    assert route.hold is not None
    assert not routed.reclaims(work_item_id=_ITEM_ID)
    assert PRESERVED_SOURCE_TERMINAL_TREE in route.hold.measurements[0].detail
    assert not any(NEEDS_HUMAN_REF_PREFIX in " ".join(call) for call in _Runner.calls)
    assert any(
        json.loads(line)["stage"] == "recovery-held"
        for line in journal.path.read_text().splitlines()
    )


def test_all_ledger_named_sources_asked_and_empty_allow_a_fresh_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _claim(repo=tmp_path)
    routed, _ = _route(repo=tmp_path, monkeypatch=monkeypatch, records=_released())

    route = routed.route_for(work_item_id=_ITEM_ID)
    assert route is not None
    assert route.route == ROUTE_FRESH
    assert route.loss is not None
    assert route.loss.source_run_id == _RUN
    assert route.loss.sources_asked == (
        PRESERVED_SOURCE_TERMINAL_TREE,
        PRESERVED_SOURCE_PUBLISHED_HEAD,
        PRESERVED_SOURCE_EARLIER_PRESERVED_PUBLISH_REF,
    )
    assert any(NEEDS_HUMAN_REF_PREFIX in " ".join(call) for call in _Runner.calls)
