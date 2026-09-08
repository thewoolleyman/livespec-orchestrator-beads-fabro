"""Integration-tier acceptance for the idle-factory attention fact.

Binds `SPECIFICATION/scenarios.md` "Scenario 120 — An idle factory with
dispatchable work surfaces its first dispatch" through the real
`build_attention` composition and the real store/client seam against the
in-memory `FakeBeadsClient`.

The clause it realizes is the idle-factory entry among the orchestrator-owned
attention facts in `SPECIFICATION/contracts.md`.

Driving the whole snapshot rather than `idle_factory_items` alone is what makes
the positive case mean anything. The scenario's claim is that ONE fact appears
and that its handoff is one `drive` accepts for that item's state — both are
properties of the composed envelope, and a lane called in isolation could show
neither. The composed pass also proves the fact does not collide with the
capacity fact it mirrors: an idle repository composes this row and no capacity
row, because they are triggered by opposite conditions.

The three clearing cases are what keep the positive one honest. Each removes
exactly ONE trigger condition from the SAME otherwise-idle fixture — a counted
claim, an unexpired provider-exhaustion record, an empty admission-eligible set
— so "the fact appeared" cannot be confused with "the fact always appears".
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_IDLE_FACT_ID = "hygiene:idle-factory:repo"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, id_: str, status: str, rank: str) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="d",
        origin="freeform",
        gap_id=None,
        rank=rank,
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, status=status)  # pyright: ignore[reportArgumentType]


def _seed(*, id_: str, status: str = "ready", rank: str = "a2") -> None:
    append_work_item(path=_config(), item=_item(id_=id_, status=status, rank=rank))


def _write_project(*, root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": "livespec-impl-beads",
                        "prefix": "bd",
                        "server_user": "livespec-impl-beads",
                        "database": "livespec-impl-beads",
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {"wip_cap": 5},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _journal(*, root: Path, records: list[dict[str, object]]) -> Path:
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return journal


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _snapshot(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def _idle_facts(*, attention: list[AttentionItem]) -> list[AttentionItem]:
    return [item for item in attention if item.id.startswith("hygiene:idle-factory")]


def _idle_fixture(*, root: Path) -> None:
    """An otherwise-idle repository: two ready items, no claim, no wait."""
    _write_project(root=root)
    _seed(id_="bd-first", rank="a1")
    _seed(id_="bd-second", rank="a2")
    _ = _journal(root=root, records=[])


def test_an_idle_factory_with_dispatchable_work_surfaces_its_first_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exactly one fact, at high urgency, naming the count and the first ranked dispatch."""
    _idle_fixture(root=tmp_path)

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    idle = _idle_facts(attention=attention)
    assert [item.id for item in idle] == [_IDLE_FACT_ID]
    assert idle[0].urgency == "high"
    assert "2 admission-eligible ready work-items" in idle[0].summary
    assert "bd-first" in idle[0].summary
    # Executable as advertised: a `drive`-kind handoff carrying the action id
    # `drive` accepts for a ready item, over this repository's own root.
    assert idle[0].handoff.kind == "drive"
    assert idle[0].handoff.action_id == "impl:bd-first"
    assert f"--repo {tmp_path} --action impl:bd-first" in idle[0].handoff.command
    # The mirror fact must not fire on the same pass: an idle factory has free
    # slots by construction, so nothing here reports capacity pressure.
    assert [item for item in attention if item.id.startswith("hygiene:capacity")] == []
    # Composing the snapshot is a read: the projection this fact consumes is the
    # side-effect-free half of the accounting pair, so the journal is untouched.
    assert (tmp_path / _JOURNAL).read_text(encoding="utf-8") == ""


def test_a_counted_claim_occupying_a_slot_clears_the_idle_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The factory is moving, so it is not idle — even with ready work behind it."""
    _idle_fixture(root=tmp_path)
    _seed(id_="bd-busy", status="active", rank="a0")
    _ = write_dispatch_lock(repo=tmp_path, work_item_id="bd-busy", dispatch_id="run-busy")

    assert _idle_facts(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch)) == []


def test_an_unexpired_provider_exhaustion_record_clears_the_idle_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """That wait already composes under provider spend containment; this row would repeat it."""
    _idle_fixture(root=tmp_path)
    _ = _journal(
        root=tmp_path,
        records=[
            {
                "at": "2099-01-01T00:00:00Z",
                "stage": "provider-exhaustion-observed",
                "work_item_id": "bd-first",
                "provider": "anthropic",
                "governing_condition": "provider_usage_limit",
                "record_expires_at": "2099-01-01T00:15:00Z",
            }
        ],
    )

    assert _idle_facts(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch)) == []


def test_no_admission_eligible_ready_item_clears_the_idle_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty queue is not an idle factory: there is nothing to dispatch."""
    _write_project(root=tmp_path)
    _seed(id_="bd-backlog", status="backlog", rank="a1")
    _ = _journal(root=tmp_path, records=[])

    assert _idle_facts(attention=_snapshot(root=tmp_path, monkeypatch=monkeypatch)) == []
