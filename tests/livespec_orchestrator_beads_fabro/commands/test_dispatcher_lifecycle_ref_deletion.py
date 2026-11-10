"""The lifecycle write seam deletes a closed item's preservation refs from origin.

Each case drives the real seam entry point (`close_work_item_and_reconcile`,
`write_work_item_status_and_reconcile`, `write_blocked_state_and_reconcile`) with
the store write and the run reconciliation stood in, and stands the forge in at the
`ShellCommandRunner` the deletion constructs, so what is asserted is what a real
close or accept would send to the forge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_ref_deletion as ref_deletion,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_lifecycle_writes as lifecycle_writes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem, WorkItemStatus

_REFS = "/repos/{owner}/{repo}/git/refs/"
_MATCHING = "/repos/{owner}/{repo}/git/matching-refs/"
_ITEM_REFS = (
    "refs/livespec/wip/bd-ib-1/01RUN/1",
    "refs/livespec/preserved-publish/bd-ib-1/abc123",
)


@dataclass(kw_only=True)
class _Forge:
    """A forge holding the item's preservation refs; every instance shares one call log."""

    refs: tuple[str, ...] = _ITEM_REFS
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
            ref = "refs/" + argv[-1].removeprefix(_REFS)
            if ref in self.refuse_delete:
                return CommandResult(exit_code=1, stdout="", stderr="HTTP 422")
            return CommandResult(exit_code=0, stdout="", stderr="")
        prefix = "refs/" + argv[3].removeprefix(_MATCHING)
        listed = [ref for ref in self.refs if ref.startswith(prefix)]
        return CommandResult(exit_code=0, stdout="\n".join(listed) + "\n", stderr="")

    @property
    def deleted(self) -> list[str]:
        return ["refs/" + call[-1].removeprefix(_REFS) for call in self.calls if "DELETE" in call]


def test_closing_an_item_deletes_its_preservation_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = _stand_in(monkeypatch=monkeypatch)

    lifecycle_writes.close_work_item_and_reconcile(
        path=_config(repo_root=tmp_path), item=_item(status="done")
    )

    assert forge.deleted == list(_ITEM_REFS)


def test_accepting_an_item_deletes_its_preservation_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = _stand_in(monkeypatch=monkeypatch)

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id="bd-ib-1", status="done"
    )

    assert forge.deleted == list(_ITEM_REFS)


@pytest.mark.parametrize("status", ["backlog", "ready", "active", "acceptance"])
def test_an_item_that_is_not_closed_keeps_every_preservation_ref(
    status: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = _stand_in(monkeypatch=monkeypatch)

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id="bd-ib-1", status=status
    )

    assert forge.calls == []


def test_resting_an_item_blocked_keeps_every_preservation_ref(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge = _stand_in(monkeypatch=monkeypatch)

    lifecycle_writes.write_blocked_state_and_reconcile(
        path=_config(repo_root=tmp_path),
        item_id="bd-ib-1",
        status="blocked",
        blocked_reason="needs-human",
    )

    assert forge.calls == []


def test_a_config_with_no_repository_deletes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    forge = _stand_in(monkeypatch=monkeypatch)

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=None), item_id="bd-ib-1", status="done"
    )

    assert forge.calls == []


def test_a_refused_deletion_is_journaled_with_its_ref_and_the_write_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    refused = _ITEM_REFS[0]
    forge = _stand_in(monkeypatch=monkeypatch, refuse_delete=frozenset({refused}))

    lifecycle_writes.write_work_item_status_and_reconcile(
        path=_config(repo_root=tmp_path), item_id="bd-ib-1", status="done"
    )

    assert forge.deleted == list(_ITEM_REFS)
    journal = (tmp_path / "tmp" / "fabro-dispatch-journal.jsonl").read_text(encoding="utf-8")
    assert '"stage": "preservation-ref-deletion-failed"' in journal
    assert f'"ref": "{refused}"' in journal


def test_an_injected_runner_is_used_in_place_of_the_shell_runner(tmp_path: Path) -> None:
    forge = _Forge()

    ref_deletion.delete_refs_after_lifecycle_write(
        path=_config(repo_root=tmp_path), item_id="bd-ib-1", status="closed", runner=forge
    )

    assert forge.deleted == list(_ITEM_REFS)


def _stand_in(
    *, monkeypatch: pytest.MonkeyPatch, refuse_delete: frozenset[str] = frozenset()
) -> _Forge:
    forge = _Forge(refuse_delete=refuse_delete)

    def _nothing(**_: object) -> None:
        return None

    monkeypatch.setattr(ref_deletion, "ShellCommandRunner", lambda: forge)
    monkeypatch.setattr(lifecycle_writes, "reconcile_after_lifecycle_write", _nothing)
    monkeypatch.setattr(lifecycle_writes.store, "append_work_item", _nothing)
    monkeypatch.setattr(lifecycle_writes.store, "update_work_item_status", _nothing)
    monkeypatch.setattr(lifecycle_writes, "update_work_item_blocked_state", _nothing)
    return forge


def _config(*, repo_root: Path | None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-orchestrator-beads-fabro",
        prefix="bd-ib",
        server_user="livespec-orchestrator-beads-fabro",
        database="livespec-orchestrator-beads-fabro",
        bd_path="bd",
        fake=True,
        repo_root=repo_root,
    )


def _item(*, status: WorkItemStatus) -> WorkItem:
    return WorkItem(
        id="bd-ib-1",
        type="task",
        status=status,
        title="bd-ib-1",
        description="d",
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
    )
