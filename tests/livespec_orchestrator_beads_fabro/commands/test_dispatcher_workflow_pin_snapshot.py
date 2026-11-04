"""The criteria wall reads workflow pins from one snapshot, not one `bd show` per item.

Measured on the live orchestrator tenant, the needs-attention gathers
`impl_next`, `idle_slot_items` and `unrunnable_acceptance_items` reached the
pinned `dispatch_workflow` through `previewed_workflow_variant`, which issued a
`bd show` per item (335 per snapshot) for a value every `bd list` record already
carries. Inside `workflow_pin_snapshot_scope` the same precedence takes the pin
from ONE list read per repository instead.

The control matters as much as the saving: every case that asserts "no show"
also asserts the ANSWER is the one the per-item read gives, because a scope that
dropped the pin would also issue no show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro._beads_client import BeadsRecord
from livespec_orchestrator_beads_fabro._beads_client_fake import FakeBeadsClient
from livespec_orchestrator_beads_fabro._store_dispatch_workflow import record_dispatch_workflow
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_workflow_pin_snapshot import (
    snapshot_pins,
    workflow_pin_snapshot_scope,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_unrunnable_acceptance import (
    unrunnable_acceptance_items,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_work_items import impl_next
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.cross_repo.types import CrossRepoManifest
from livespec_runtime.needs_attention import SpecNextOutput

_GROOM_VARIANT = "groom-cut"
_IMPLEMENT_VARIANT = "slice"
_GROOM_DIR = f".fabro/workflows/{_GROOM_VARIANT}"
_IMPLEMENT_DIR = f".fabro/workflows/{_IMPLEMENT_VARIANT}"
_GROOM_TOML = '[workflow]\ngraph = "workflow.fabro"\n\n[run.inputs]\nworkflow_kind = "groom"\n'
_IMPLEMENT_TOML = '[workflow]\ngraph = "workflow.fabro"\n'
_SPEC_HEADING = "## Effective acceptance criteria"
_REPO_NAME = "repo"


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, item_id: str) -> WorkItem:
    return WorkItem(
        id=item_id,
        type="task",
        status="ready",
        title="A ready task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-25T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {"prefix": "bd-ib", "fake": True},
                    "dispatcher": {
                        "workflows": {
                            _GROOM_VARIANT: _GROOM_DIR,
                            _IMPLEMENT_VARIANT: _IMPLEMENT_DIR,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    for directory, text in ((_GROOM_DIR, _GROOM_TOML), (_IMPLEMENT_DIR, _IMPLEMENT_TOML)):
        (repo / directory).mkdir(parents=True, exist_ok=True)
        _ = (repo / directory / "workflow.toml").write_text(text, encoding="utf-8")
    spec = repo / "SPECIFICATION"
    spec.mkdir(exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _file(*, item_id: str, workflow: str | None) -> WorkItem:
    item = _item(item_id=item_id)
    append_work_item(path=_config(), item=item)
    if workflow is not None:
        record_dispatch_workflow(path=_config(), work_item_id=item_id, workflow=workflow)
    return item


class _Calls:
    def __init__(self) -> None:
        self.shown: list[str] = []
        self.listed = 0


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    recorded = _Calls()
    real_show = FakeBeadsClient.show_issue
    real_list = FakeBeadsClient.list_issues

    def _show(self: FakeBeadsClient, *, issue_id: str) -> BeadsRecord:
        recorded.shown.append(issue_id)
        return real_show(self, issue_id=issue_id)

    def _list(self: FakeBeadsClient) -> list[BeadsRecord]:
        recorded.listed += 1
        return real_list(self)

    monkeypatch.setattr(FakeBeadsClient, "show_issue", _show)
    monkeypatch.setattr(FakeBeadsClient, "list_issues", _list)
    return recorded


def test_inside_the_scope_a_groom_pin_resolves_exempt_with_no_show(
    tmp_path: Path, calls: _Calls
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _file(item_id="bd-ib-snapgroom", workflow=_GROOM_VARIANT)
    _ = _file(item_id="bd-ib-snapimpl", workflow=_IMPLEMENT_VARIANT)
    calls.shown.clear()

    with workflow_pin_snapshot_scope():
        groom = criteria_wall_variant(repo=repo, work_item_id="bd-ib-snapgroom")
        impl = criteria_wall_variant(repo=repo, work_item_id="bd-ib-snapimpl")

    assert (groom.name, groom.exempt) == (_GROOM_VARIANT, True)
    assert (impl.name, impl.exempt) == (_IMPLEMENT_VARIANT, False)
    assert calls.shown == []


def test_outside_any_scope_the_per_item_read_still_answers(tmp_path: Path, calls: _Calls) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _file(item_id="bd-ib-snapalone", workflow=_GROOM_VARIANT)
    calls.shown.clear()

    variant = criteria_wall_variant(repo=repo, work_item_id="bd-ib-snapalone")

    assert (variant.name, variant.exempt) == (_GROOM_VARIANT, True)
    assert "bd-ib-snapalone" in calls.shown


def test_the_scope_lists_the_tenant_once_however_many_items_it_resolves(
    tmp_path: Path, calls: _Calls
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ids = [f"bd-ib-snapmany{n}" for n in range(3)]
    for item_id in ids:
        _ = _file(item_id=item_id, workflow=_IMPLEMENT_VARIANT)
    calls.listed = 0

    with workflow_pin_snapshot_scope():
        with workflow_pin_snapshot_scope():
            for item_id in ids:
                _ = criteria_wall_variant(repo=repo, work_item_id=item_id)
        for item_id in ids:
            _ = criteria_wall_variant(repo=repo, work_item_id=item_id)

    assert calls.listed == 1


def test_an_item_the_snapshot_does_not_carry_falls_back_to_the_per_item_read(
    tmp_path: Path, calls: _Calls
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _file(item_id="bd-ib-snapold", workflow=_IMPLEMENT_VARIANT)

    with workflow_pin_snapshot_scope():
        assert snapshot_pins(repo=repo) == {"bd-ib-snapold": _IMPLEMENT_VARIANT}
        _ = _file(item_id="bd-ib-snaplate", workflow=_GROOM_VARIANT)
        calls.shown.clear()
        late = criteria_wall_variant(repo=repo, work_item_id="bd-ib-snaplate")

    assert (late.name, late.exempt) == (_GROOM_VARIANT, True)
    assert calls.shown == ["bd-ib-snaplate"]


def test_an_unreadable_snapshot_degrades_to_the_per_item_read(
    tmp_path: Path, calls: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    _ = _file(item_id="bd-ib-snapdown", workflow=_GROOM_VARIANT)

    def _refuse(self: FakeBeadsClient) -> list[BeadsRecord]:
        _ = self
        raise OSError("tenant list refused")

    monkeypatch.setattr(FakeBeadsClient, "list_issues", _refuse)
    calls.shown.clear()

    with workflow_pin_snapshot_scope():
        assert snapshot_pins(repo=repo) is None
        variant = criteria_wall_variant(repo=repo, work_item_id="bd-ib-snapdown")

    assert (variant.name, variant.exempt) == (_GROOM_VARIANT, True)
    assert calls.shown == ["bd-ib-snapdown"]


def test_no_snapshot_exists_outside_a_scope(tmp_path: Path) -> None:
    assert snapshot_pins(repo=_repo(tmp_path=tmp_path)) is None


def test_the_unrunnable_acceptance_lane_issues_no_show_and_answers_the_same(
    tmp_path: Path, calls: _Calls
) -> None:
    repo = _repo(tmp_path=tmp_path)
    items = [
        _file(item_id="bd-ib-lanegroom", workflow=_GROOM_VARIANT),
        _file(item_id="bd-ib-laneimpl", workflow=_IMPLEMENT_VARIANT),
        _file(item_id="bd-ib-laneplain", workflow=None),
    ]
    unscoped = unrunnable_acceptance_items(project_root=repo, repo=_REPO_NAME, items=items)
    calls.shown.clear()

    with workflow_pin_snapshot_scope():
        scoped = unrunnable_acceptance_items(project_root=repo, repo=_REPO_NAME, items=items)

    assert [fact.id for fact in scoped] == [fact.id for fact in unscoped]
    assert [fact.id for fact in scoped] == [
        "hygiene:unrunnable-acceptance:bd-ib-laneimpl",
        "hygiene:unrunnable-acceptance:bd-ib-laneplain",
    ]
    assert calls.shown == []


def test_impl_next_issues_no_show_for_the_ready_items(tmp_path: Path, calls: _Calls) -> None:
    repo = _repo(tmp_path=tmp_path)
    items = [
        _file(item_id="bd-ib-nextgroom", workflow=_GROOM_VARIANT),
        _file(item_id="bd-ib-nextimpl", workflow=_IMPLEMENT_VARIANT),
    ]
    calls.shown.clear()

    with workflow_pin_snapshot_scope():
        picked = impl_next(project_root=repo, items=items, manifest=CrossRepoManifest(targets={}))

    assert picked is not None
    assert picked.work_item == "bd-ib-nextgroom"
    assert calls.shown == []


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def test_the_composed_attention_pass_reads_no_pin_through_a_show(
    tmp_path: Path, calls: _Calls, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path=tmp_path)
    ready_ids = ["bd-ib-passgroom", "bd-ib-passimpl", "bd-ib-passplain"]
    for item_id, workflow in zip(
        ready_ids, (_GROOM_VARIANT, _IMPLEMENT_VARIANT, None), strict=True
    ):
        _ = _file(item_id=item_id, workflow=workflow)
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    calls.shown.clear()

    attention: list[Any] = build_attention(
        project_root=repo, repo_name=_REPO_NAME, include_hygiene=False
    )

    assert [fact.id for fact in attention if "unrunnable" in fact.id] == [
        "hygiene:unrunnable-acceptance:bd-ib-passimpl",
        "hygiene:unrunnable-acceptance:bd-ib-passplain",
    ]
    assert [shown for shown in calls.shown if shown in ready_ids] == []
