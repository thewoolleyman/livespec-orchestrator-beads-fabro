"""Integration-tier acceptance for the `set-factory-safety:<id>:<reason>` valve.

Binds the SPECIFICATION/scenarios.md `set-factory-safety` scenarios through the
public `drive.run_action` surface and the real store/client seam against the
in-memory `FakeBeadsClient`. The cases pin what contracts.md binds: the verb is
the ONLY attributable route out of factory eligibility, its reason MUST be one of
the three canonical `factory_safety` values, it is valid in ANY lane because
`factory_safety` is an intrinsic runnability axis rather than a lifecycle state,
and it changes neither the item's status nor its `admission_policy`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import fake_singleton, reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
from livespec_orchestrator_beads_fabro.commands._drive_valve_grammar import is_human_valve_action
from livespec_orchestrator_beads_fabro.commands.drive import run_action
from livespec_orchestrator_beads_fabro.store import (
    append_work_item,
    materialize_work_items,
    read_work_items,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"


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
        status="backlog",
        title="A backlog task",
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
        admission_policy="auto",
    )
    return replace(base, **overrides)


def _stored() -> WorkItem:
    return materialize_work_items(records=read_work_items(path=_config()))["bd-ib-123"]


def test_set_factory_safety_records_the_opt_out_reason_on_a_backlog_item(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item())

    result = run_action(
        repo=repo,
        action_id="set-factory-safety:bd-ib-123:needs-host-secrets",
        identity=InvokerIdentity(invoker="human:cw", invoker_source="flag"),
    )

    assert result["status"] == "green"
    assert result["target_status"] == "backlog"
    assert result["journal"] == {
        "actor": "operator",
        "stage": "human-valve-set-factory-safety",
        "work_item_id": "bd-ib-123",
        "factory_safety": "needs-host-secrets",
    }
    stored = _stored()
    assert stored.factory_safety == "needs-host-secrets"
    assert stored.status == "backlog"
    assert stored.admission_policy == "auto"
    journal = (repo / _JOURNAL).read_text(encoding="utf-8")
    assert "needs-host-secrets" in journal
    assert '"invoker": "human:cw"' in journal


def test_set_factory_safety_is_not_gated_by_lifecycle_state(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="acceptance", assignee="alice"))

    result = run_action(repo=repo, action_id="set-factory-safety:bd-ib-123:mutates-host-machinery")

    assert result["status"] == "green"
    assert result["target_status"] == "acceptance"
    assert result["assignee"] == "alice"
    stored = _stored()
    assert stored.factory_safety == "mutates-host-machinery"
    assert stored.status == "acceptance"


def test_set_factory_safety_replaces_a_previously_recorded_reason(tmp_path: Path) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(factory_safety="needs-host-secrets"))

    result = run_action(repo=repo, action_id="set-factory-safety:bd-ib-123:needs-privileged-host")

    assert result["status"] == "green"
    assert _stored().factory_safety == "needs-privileged-host"
    labels = fake_singleton().show_issue(issue_id="bd-ib-123")["labels"]
    assert "factory-safety:needs-privileged-host" in labels
    assert "factory-safety:needs-host-secrets" not in labels


@pytest.mark.parametrize("reason", ["not-a-real-reason", ""])
def test_set_factory_safety_refuses_a_reason_outside_the_canonical_enum(
    tmp_path: Path, reason: str
) -> None:
    repo = _repo(tmp_path=tmp_path)
    append_work_item(path=_config(), item=_item(status="ready"))

    result = run_action(repo=repo, action_id=f"set-factory-safety:bd-ib-123:{reason}")

    assert result["status"] == "failed"
    assert result["domain_error"] == "invalid-factory-safety-reason"
    summary = str(result["summary"])
    assert "needs-host-secrets" in summary
    assert "mutates-host-machinery" in summary
    assert "needs-privileged-host" in summary
    stored = _stored()
    assert stored.factory_safety is None
    assert stored.status == "ready"
    assert not (repo / _JOURNAL).exists()


def test_set_factory_safety_is_registered_in_the_drive_action_id_grammar(
    tmp_path: Path,
) -> None:
    assert is_human_valve_action(action_id="set-factory-safety:bd-ib-123:needs-host-secrets")

    repo = _repo(tmp_path=tmp_path)
    unsupported = run_action(repo=repo, action_id="not-a-verb:bd-ib-123:value")

    assert unsupported["kind"] == "unknown"
    assert "set-factory-safety:<id>:" in str(unsupported["summary"])
