"""Scenario 187 — the priority-epic idle-slot audit, end to end.

The four sub-scenarios of Scenario 187 in `SPECIFICATION/scenarios.md` are
asserted here against the real configuration reader, the real tenant reader,
the real board projection and the real needs-attention composition. Only two
things are substituted, and each is a substrate rather than a decision: the
beads backend is the hermetic in-memory one, and `fabro ps` is a canned run
listing, because a test that reached a factory would assert the factory's
mood rather than this surface's behaviour.

ONE LIMIT OF THE FIXTURE, STATED SO IT IS NOT MISREAD AS COVERAGE. The
hermetic beads backend is a process-wide singleton, so the second checkout
below reads the same in-memory store as the first. What this file therefore
proves about cross-tenant reading is that each entry's `repo` is RESOLVED and
READ as its own checkout — the paths the reader is handed, and the config it
resolves there. That every entry reaches a DIFFERENT store is proved in
`tests/livespec_orchestrator_beads_fabro/commands/test_dispatcher_idle_slot_audit.py`,
which hands the audit a per-path tenant reader and asserts which paths it
asked for.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import _dispatcher_idle_slot_board as board_module
from livespec_orchestrator_beads_fabro.commands import needs_attention as needs_attention_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_audit import idle_slot_audit
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_command import (
    run_idle_slot_audit_command,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.needs_attention import SpecNextOutput

_TENANT = "priority-tenant"
_EPIC = "pt-epic"
_FACTORY = "hp"
_FACT_ID = f"hygiene:idle-slot:{_FACTORY}"
_SPEC_HEADING = "## Effective acceptance criteria"
_DEFINITION_OF_DONE = (
    "## Definition of Done\n"
    "\n"
    "- The idle-slot audit classifies this item.\n"
    "\n"
    f"References: {_SPEC_HEADING}\n"
)


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant=_TENANT,
        prefix="pt",
        server_user=_TENANT,
        database=_TENANT,
        bd_path="bd",
        fake=True,
    )


def _item(*, id_: str, status: str = "ready", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title=f"{id_} title",
        description=_DEFINITION_OF_DONE,
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-16T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _seed(*items: WorkItem) -> None:
    for item in items:
        append_work_item(path=_config(), item=item)


def _write_checkout(root: Path, *, dispatcher: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": "pt",
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": dispatcher,
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text("", encoding="utf-8")


def _write_project(root: Path) -> Path:
    """The governed checkout plus the priority tenant's own checkout beside it."""
    tenant_root = root / "priority-checkout"
    _write_checkout(
        root,
        dispatcher={
            "wip_cap": 5,
            "factories": {_FACTORY: {"server": "https://hp.example:32276"}},
            "idle_slot_audit": {
                "factory": _FACTORY,
                "priority": [{"repo": "priority-checkout", "epic": _EPIC}],
            },
        },
    )
    _write_checkout(tenant_root, dispatcher={"wip_cap": 5})
    return tenant_root


def _run(*, run_id: str, status: str, work_item: str | None = None) -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind=status,
        goal=None if work_item is None else f"Work-item: {work_item}\n",
        total_usd_micros=None,
        work_item_id=work_item,
    )


def _install_board(
    monkeypatch: pytest.MonkeyPatch,
    *,
    runs: tuple[FabroRunSummary, ...] | None,
) -> None:
    """Stand in for `fabro ps -a --json` at the port boundary, not above it."""

    class _Reader:
        def __init__(self, *, repo: Path) -> None:
            self._repo = repo

        def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
            _ = factory
            return runs

    monkeypatch.setattr(board_module, "FactoryRunReader", _Reader)


def _classes(result: object) -> dict[str, str]:
    return {child.id: child.classification for entry in result.entries for child in entry.children}


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _no_watchable_runs(*, repo: Path) -> frozenset[str]:
    _ = repo
    return frozenset()


def _snapshot(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> list[object]:
    monkeypatch.setattr(needs_attention_module, "spec_next", _no_spec_next)
    monkeypatch.setattr(needs_attention_module, "watchable_fabro_run_item_ids", _no_watchable_runs)
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def test_an_empty_queue_beside_a_dispatchable_child_produces_the_finding_and_the_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sub-scenario 1: the finding line is last, and exactly one fact composes."""
    _ = _write_project(tmp_path)
    _seed(_item(id_=f"{_EPIC}.1"))
    _install_board(monkeypatch, runs=(_run(run_id="r1", status="running", work_item="other"),))
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    before = journal.read_bytes()

    exit_code = run_idle_slot_audit_command(
        args=argparse.Namespace(repo=str(tmp_path), as_json=False)
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line != ""]
    assert exit_code == 0
    assert f"{_EPIC}.1  DISPATCHABLE-NOW" in "\n".join(lines)
    assert lines[-1].startswith(f"FINDING: factory {_FACTORY} shows no runnable run with 1 live")
    assert f"{_EPIC}.1" in lines[-1]
    assert journal.read_bytes() == before

    facts = [
        item for item in _snapshot(root=tmp_path, monkeypatch=monkeypatch) if item.id == _FACT_ID
    ]
    assert len(facts) == 1
    assert facts[0].handoff.kind == "shell"
    assert "idle-slot-audit" in facts[0].handoff.command


def test_a_blocker_with_a_live_run_is_blocked_and_without_one_is_a_stale_edge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sub-scenario 2: `active` means in flight, not landed."""
    tenant_root = _write_project(tmp_path)
    _seed(
        _item(id_=f"{_EPIC}.blocker", status="active", assignee="fabro"),
        _item(
            id_=f"{_EPIC}.dependent",
            depends_on=({"kind": "local", "work_item_id": f"{_EPIC}.blocker"},),
        ),
    )
    _install_board(
        monkeypatch,
        runs=(_run(run_id="r1", status="running", work_item=f"{_EPIC}.blocker"),),
    )

    blocked = idle_slot_audit(project_root=tmp_path)

    assert _classes(blocked)[f"{_EPIC}.dependent"] == "BLOCKED"
    assert blocked.finding is None

    _install_board(monkeypatch, runs=())
    stale = idle_slot_audit(project_root=tmp_path)

    assert _classes(stale)[f"{_EPIC}.dependent"] == "STALE-EDGE"
    assert stale.finding is not None
    assert stale.finding.stale_edge_ids == (f"{_EPIC}.dependent",)
    assert tenant_root.is_dir()


def test_the_verdict_holds_a_child_while_a_comment_cannot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sub-scenario 3: a hold lives in status or the verdict, never in prose."""
    _ = _write_project(tmp_path)
    _seed(
        _item(id_=f"{_EPIC}.held", description="No Definition of Done in this one."),
        _item(id_=f"{_EPIC}.prose"),
    )
    client = make_beads_client(config=_config())
    client.add_comment(issue_id=f"{_EPIC}.prose", body="HELD by driver ruling R68.")
    _install_board(monkeypatch, runs=())

    result = idle_slot_audit(project_root=tmp_path)
    classes = _classes(result)
    held = next(
        child for entry in result.entries for child in entry.children if child.id == f"{_EPIC}.held"
    )

    assert classes[f"{_EPIC}.held"] == "HELD"
    assert held.reason is not None
    assert classes[f"{_EPIC}.prose"] == "DISPATCHABLE-NOW"


def test_a_queued_row_or_an_unreadable_board_yields_no_finding_and_no_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sub-scenario 4: something already waits, or nobody could look."""
    _ = _write_project(tmp_path)
    _seed(_item(id_=f"{_EPIC}.1"))

    _install_board(monkeypatch, runs=(_run(run_id="r1", status="runnable", work_item="other"),))
    queued = idle_slot_audit(project_root=tmp_path)

    assert _classes(queued)[f"{_EPIC}.1"] == "DISPATCHABLE-NOW"
    assert queued.finding is None
    assert [
        item for item in _snapshot(root=tmp_path, monkeypatch=monkeypatch) if item.id == _FACT_ID
    ] == []

    _install_board(monkeypatch, runs=None)
    exit_code = run_idle_slot_audit_command(
        args=argparse.Namespace(repo=str(tmp_path), as_json=False)
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "board: UNOBSERVABLE — live unknown, queued unknown" in out
    assert "FINDING" not in out
    assert [
        item for item in _snapshot(root=tmp_path, monkeypatch=monkeypatch) if item.id == _FACT_ID
    ] == []


def test_an_edge_linked_child_in_the_priority_tenant_is_enumerated_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The edge arm of the union, beside the dotted-id arm the others exercise."""
    _ = _write_project(tmp_path)
    _seed(_item(id_=_EPIC, status="backlog"), _item(id_="pt-edge-child"))
    client = make_beads_client(config=_config())
    client.add_dependency(from_id="pt-edge-child", to_id=_EPIC, edge_type="parent-child")
    _install_board(monkeypatch, runs=())

    result = idle_slot_audit(project_root=tmp_path)

    assert "pt-edge-child" in _classes(result)
