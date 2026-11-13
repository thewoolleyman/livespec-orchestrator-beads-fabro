"""Acceptance coverage for the `close-duplicate` human valve."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_BLOCKS,
    EDGE_SUPERSEDES,
    BeadsRecord,
    fake_singleton,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro._store_supersession import superseded_by_from_records
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import CommandRunner
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_DUPLICATE = "bd-ib-duplicate"
_SUCCESSOR = "bd-ib-successor"


@dataclass(frozen=True, kw_only=True)
class _Run:
    returncode: int
    stdout: str = "[]"
    stderr: str = ""
    argv: tuple[str, ...] = ()


@dataclass(kw_only=True)
class _Runner:
    result: _Run = field(default_factory=lambda: _Run(returncode=0))

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> _Run:
        _ = (argv, cwd)
        return self.result


@pytest.fixture(autouse=True)
def _fake_beads_env(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"connection": {"prefix": "bd-ib"}}}',
        encoding="utf-8",
    )
    return repo


def _item(*, item_id: str, status: str = "blocked") -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
        title="A work item",
        description="## Definition of Done\n\n- A verifiable slice.\n",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-05T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        acceptance_criteria="A verifiable slice is delivered.",
    )


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_supersession_projection_ignores_other_dependency_kinds() -> None:
    assert (
        superseded_by_from_records(
            records=cast(
                "list[BeadsRecord]",
                [
                    {
                        "id": _SUCCESSOR,
                        "dependencies": [{"depends_on_id": _DUPLICATE, "type": EDGE_BLOCKS}],
                    }
                ],
            ),
        )
        == {}
    )


@pytest.mark.parametrize(
    "status", ["backlog", "pending-approval", "ready", "active", "acceptance", "blocked"]
)
def test_close_duplicate_closes_every_non_terminal_lane_and_records_successor(
    tmp_path: Path, status: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(item_id=_DUPLICATE, status=status))
    append_work_item(path=_config(), item=_item(item_id=_SUCCESSOR, status="backlog"))
    identity = InvokerIdentity(invoker="human:chad", invoker_source="flag")

    result = run_action(
        repo=repo,
        action_id=f"close-duplicate:{_DUPLICATE}:{_SUCCESSOR}",
        runner=cast("CommandRunner", _Runner()),
        identity=identity,
    )

    assert result["status"] == "green"
    assert result["target_status"] == "done"
    assert result["successor"] == _SUCCESSOR
    assert _stored()[_DUPLICATE].status == "done"
    assert _stored()[_DUPLICATE].superseded_by == _SUCCESSOR
    successor = fake_singleton().show_issue(issue_id=_SUCCESSOR)
    assert {"depends_on_id": _DUPLICATE, "type": EDGE_SUPERSEDES} in successor["dependencies"]
    comments = read_work_item_comments(path=_config(), work_item_id=_DUPLICATE)
    assert comments[-1].text == "close-duplicate\n\nsuccessor: bd-ib-successor\ninvoker: human:chad"
    journal = json.loads((repo / "tmp" / "fabro-dispatch-journal.jsonl").read_text())
    assert journal["work_item_id"] == _DUPLICATE
    assert journal["successor"] == _SUCCESSOR
    assert journal["invoker"] == "human:chad"


@pytest.mark.parametrize(
    ("action", "status", "runner"),
    [
        (f"close-duplicate:{_DUPLICATE}:missing", "blocked", _Runner()),
        (f"close-duplicate:{_DUPLICATE}:{_DUPLICATE}", "blocked", _Runner()),
        (f"close-duplicate:{_DUPLICATE}:{_SUCCESSOR}", "done", _Runner()),
        (
            f"close-duplicate:{_DUPLICATE}:{_SUCCESSOR}",
            "blocked",
            _Runner(
                result=_Run(
                    returncode=0,
                    stdout='[{"run_id": "01MLIVE", "status": "running", "goal": "Work-item: bd-ib-duplicate"}]',
                )
            ),
        ),
        (
            f"close-duplicate:{_DUPLICATE}:{_SUCCESSOR}",
            "blocked",
            _Runner(result=_Run(returncode=1)),
        ),
    ],
)
def test_close_duplicate_refusals_leave_the_ledger_and_journal_unchanged(
    tmp_path: Path, action: str, status: str, runner: _Runner
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(item_id=_DUPLICATE, status=status))
    append_work_item(path=_config(), item=_item(item_id=_SUCCESSOR, status="backlog"))

    result = run_action(repo=repo, action_id=action, runner=cast("CommandRunner", runner))

    assert result["status"] == "failed"
    assert _stored()[_DUPLICATE].status == status
    assert read_work_item_comments(path=_config(), work_item_id=_DUPLICATE) == ()
    assert not (repo / "tmp" / "fabro-dispatch-journal.jsonl").exists()
    assert fake_singleton().show_issue(issue_id=_SUCCESSOR)["dependencies"] == []


def test_close_duplicate_refuses_an_unreleased_dispatch_claim(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(item_id=_DUPLICATE))
    append_work_item(path=_config(), item=_item(item_id=_SUCCESSOR, status="backlog"))
    _ = write_dispatch_lock(repo=repo, work_item_id=_DUPLICATE, dispatch_id="dispatch-1")

    result = run_action(
        repo=repo,
        action_id=f"close-duplicate:{_DUPLICATE}:{_SUCCESSOR}",
        runner=cast("CommandRunner", _Runner()),
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "dispatch-lock-held"
    assert _stored()[_DUPLICATE].status == "blocked"
    assert read_work_item_comments(path=_config(), work_item_id=_DUPLICATE) == ()
