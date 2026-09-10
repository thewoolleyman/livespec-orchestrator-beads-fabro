"""Tests for `set-factory-safety` — the one human valve that NO lane gates.

Every sibling valve asserts a source state; this one asserts the ABSENCE of one,
so the coverage carrying the contract is the same press landing from several
different lanes (the status-independent verbs clause of contracts.md). Each
assertion about what the valve DID reads the item back through the store seam
rather than trusting the payload the valve returned: a valve that reports green
while writing nothing is precisely the failure a return-value assertion cannot
see.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient, make_beads_client
from livespec_orchestrator_beads_fabro.commands._drive_valves import run_human_valve_action
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_ITEM_ID = "bd-ib-ready"
_FACTORY_SAFETY_PREFIX = "factory-safety:"
_REASONS = ("needs-host-secrets", "mutates-host-machinery", "needs-privileged-host")


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="livespec-impl-beads",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def _labels() -> list[str]:
    raw = _fake().show_issue(issue_id=_ITEM_ID)["labels"]
    assert isinstance(raw, list)
    return [str(label) for label in raw]


def _stored() -> WorkItem:
    return next(item for item in read_work_items(path=_config()) if item.id == _ITEM_ID)


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id=_ITEM_ID,
        type="task",
        status="ready",
        title="Ready",
        description="d",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-07-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _repo(tmp_path: Path, *, status: str = "ready", **overrides: object) -> Path:
    """A repo whose fake tenant holds one item, parked in the requested lane.

    The lane is reached by a SECOND append rather than by filing straight into
    it, so `done` arrives through the store's real close path exactly as it
    would in life — which is the lane the status-independence clause is most
    easily read as excluding.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".livespec.jsonc").write_text(
        """{
  "livespec-orchestrator-beads-fabro": {
    "connection": {
      "tenant": "livespec-impl-beads",
      "prefix": "bd",
      "server_user": "livespec-impl-beads",
      "database": "livespec-impl-beads",
      "bd_path": "bd",
      "fake": true
    }
  }
}
""",
        encoding="utf-8",
    )
    append_work_item(path=_config(), item=_item(**overrides))
    if status != "ready":
        append_work_item(path=_config(), item=_item(status=status, **overrides))
    return repo


@pytest.mark.parametrize("reason", _REASONS)
def test_the_valve_records_each_canonical_reason_on_the_item(tmp_path: Path, reason: str) -> None:
    repo = _repo(tmp_path, status="backlog")

    result = run_human_valve_action(repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:{reason}")

    assert result["status"] == "green"
    assert result["journal"] == {
        "actor": "operator",
        "stage": "human-valve-set-factory-safety",
        "work_item_id": _ITEM_ID,
    }
    assert _stored().factory_safety == reason


@pytest.mark.parametrize(
    "status",
    ["backlog", "pending-approval", "ready", "active", "acceptance", "blocked", "done"],
)
def test_the_valve_is_not_gated_by_lifecycle_state(tmp_path: Path, status: str) -> None:
    """Valid in ANY lane, the `done` row included, per contracts.md's status-independence."""
    repo = _repo(tmp_path, status=status)

    result = run_human_valve_action(
        repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:mutates-host-machinery"
    )

    assert result["status"] == "green"
    assert result["target_status"] == status
    assert _stored().status == status
    assert _stored().factory_safety == "mutates-host-machinery"


def test_the_valve_refuses_a_reason_outside_the_factory_safety_enum(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    result = run_human_valve_action(
        repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:not-a-real-reason"
    )

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-action-id"
    assert _stored().factory_safety is None


def test_the_valve_refuses_an_empty_reason(tmp_path: Path) -> None:
    """The rationale is MANDATORY, so an empty trailing field is not a weaker press."""
    repo = _repo(tmp_path)

    result = run_human_valve_action(repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:")

    assert result["status"] == "failed"
    assert _stored().factory_safety is None


def test_the_valve_leaves_the_admission_policy_alone(tmp_path: Path) -> None:
    """`admission_policy` is the orthogonal human-approval axis, not this one."""
    repo = _repo(tmp_path, admission_policy="manual")

    result = run_human_valve_action(
        repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:needs-privileged-host"
    )

    assert result["status"] == "green"
    assert _stored().admission_policy == "manual"


def test_resetting_the_axis_replaces_the_recorded_reason(tmp_path: Path) -> None:
    """One item carries ONE reason: a second press must not leave two labels behind."""
    repo = _repo(tmp_path)
    _ = run_human_valve_action(
        repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:needs-host-secrets"
    )

    _ = run_human_valve_action(
        repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:needs-privileged-host"
    )

    assert [label for label in _labels() if label.startswith(_FACTORY_SAFETY_PREFIX)] == [
        f"{_FACTORY_SAFETY_PREFIX}needs-privileged-host"
    ]
    assert _stored().factory_safety == "needs-privileged-host"


def test_drives_own_grammar_registers_the_action(tmp_path: Path) -> None:
    """`drive`'s own router, not just the valve router, admits `set-factory-safety:`."""
    repo = _repo(tmp_path)

    result = run_action(repo=repo, action_id=f"set-factory-safety:{_ITEM_ID}:needs-host-secrets")

    assert result["kind"] == "human-valve"
    assert result["status"] == "green"
    assert _stored().factory_safety == "needs-host-secrets"


def test_the_unsupported_action_summary_enumerates_the_verb(tmp_path: Path) -> None:
    """That summary is the only enumeration of the verb set an operator ever sees."""
    result = run_action(repo=tmp_path, action_id="not-an-action")

    assert "set-factory-safety:<id>:" in str(result["summary"])
