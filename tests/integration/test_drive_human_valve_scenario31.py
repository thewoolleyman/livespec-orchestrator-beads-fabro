"""Integration-tier acceptance for Scenario 31 drive operator actions.

Binds SPECIFICATION/scenarios.md "Scenario 31 — drive human valve actions"
through the public `drive.run_action` surface and the real store/client
seam against the in-memory `FakeBeadsClient`. The cases pin the ratified
approval model: `approve:<id>` is the human approval act
`pending-approval -> ready`, and policy-edit actions change only labels, never
status.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
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


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-123",
        type="task",
        status="pending-approval",
        title="A pending task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="manual",
        acceptance_policy="ai-then-human",
    )
    return replace(base, **overrides)


def _stored() -> dict[str, WorkItem]:
    return materialize_work_items(records=read_work_items(path=_config()))


def test_approve_authorizes_pending_manual_item_into_ready(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    result = run_action(repo=repo, action_id="approve:bd-ib-123")

    assert result["status"] == "green"
    assert result["target_status"] == "ready"
    assert result["journal"] == {
        "actor": "operator",
        "stage": "human-valve-approve",
        "work_item_id": "bd-ib-123",
    }
    stored = _stored()["bd-ib-123"]
    assert stored.status == "ready"
    assert stored.assignee is None


def test_set_admission_edits_policy_without_approving_pending_item(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    result = run_action(repo=repo, action_id="set-admission:bd-ib-123:auto")

    assert result["status"] == "green"
    assert result["target_status"] == "pending-approval"
    stored = _stored()["bd-ib-123"]
    assert stored.admission_policy == "auto"
    assert stored.status == "pending-approval"


def test_set_acceptance_edits_policy_without_touching_status(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(
        path=_config(),
        item=_item(status="acceptance", assignee="alice", acceptance_policy="ai-then-human"),
    )

    result = run_action(repo=repo, action_id="set-acceptance:bd-ib-123:human-only")

    assert result["status"] == "green"
    assert result["assignee"] == "alice"
    assert result["target_status"] == "acceptance"
    stored = _stored()["bd-ib-123"]
    assert stored.acceptance_policy == "human-only"
    assert stored.status == "acceptance"
