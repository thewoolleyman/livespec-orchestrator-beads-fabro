"""Integration-tier acceptance for journal-recorded holds in needs-attention.

Binds `SPECIFICATION/scenarios.md` "Scenario 324 — A hold recorded only in the
dispatch journal reaches needs-attention" through the real `build_attention`
composition and the real store/client seam against the in-memory
`FakeBeadsClient`.

The clause it realizes is "Journal-recorded holds" among the orchestrator-owned
attention facts in `SPECIFICATION/contracts.md`.

Driving the whole snapshot is what makes the cases mean anything. The scenario's
claims are about what the SNAPSHOT carries — one fact for a hold, no fact for a
retired one, and an idle-factory fact that no longer counts a held item — and
the second kind is a relation between two lanes that neither lane shows alone.
Every case seeds the SAME otherwise-idle fixture (two ready, admission-eligible
items) so the hold under test is the only variable: an idle-factory fact naming
the held item's neighbour is evidence the neighbour stayed dispatchable, and its
absence beside a hold on the only ready item is evidence the hold cleared it.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro.commands import needs_attention
from livespec_orchestrator_beads_fabro.commands.needs_attention import build_attention
from livespec_orchestrator_beads_fabro.store import append_work_item
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.attention_item import AttentionItem
from livespec_runtime.needs_attention import SpecNextOutput

_JOURNAL = Path("tmp") / "fabro-dispatch-journal.jsonl"
_SPEC_HEADING = "## Effective acceptance criteria"
_DEFINITION_OF_DONE = (
    "## Definition of Done\n"
    "\n"
    "- The journal-hold fact names this item.\n"
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
        tenant="livespec-impl-beads",
        prefix="bd",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item(*, id_: str, rank: str) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description=_DEFINITION_OF_DONE,
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
    return replace(base)


def _write_project(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
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
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )


def _stamp(*, days: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _journal(*, root: Path, records: list[dict[str, object]]) -> None:
    journal = root / _JOURNAL
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _no_spec_next(*, project_root: Path) -> SpecNextOutput | None:
    _ = project_root
    return None


def _fixture(*, root: Path, records: list[dict[str, object]]) -> None:
    """An otherwise-idle repository: two ready items, no claim, no wait."""
    _write_project(root=root)
    append_work_item(path=_config(), item=_item(id_="bd-held", rank="a1"))
    append_work_item(path=_config(), item=_item(id_="bd-free", rank="a2"))
    _journal(root=root, records=records)


def _snapshot(*, root: Path, monkeypatch: pytest.MonkeyPatch) -> list[AttentionItem]:
    monkeypatch.setattr(needs_attention, "spec_next", _no_spec_next)
    return build_attention(project_root=root, repo_name="repo", include_hygiene=False)


def _ids(*, attention: list[AttentionItem], prefix: str) -> list[str]:
    return [item.id for item in attention if item.id.startswith(prefix)]


def test_a_recovery_held_item_reaches_needs_attention_and_is_not_reported_idle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One fact naming every reason, and the idle row names the neighbour, not the held item."""
    _fixture(
        root=tmp_path,
        records=[
            {
                "at": _stamp(),
                "stage": "recovery-held",
                "work_item_id": "bd-held",
                "measurements": ["published-head-unreadable"],
                "refusals": ["preserved-ref-unreadable"],
            }
        ],
    )

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert _ids(attention=attention, prefix="hygiene:journal-hold") == [
        "hygiene:journal-hold:bd-held"
    ]
    fact = next(item for item in attention if item.id == "hygiene:journal-hold:bd-held")
    for needle in ("recovery-held", "published-head-unreadable", "preserved-ref-unreadable"):
        assert needle in fact.summary
    assert fact.handoff.kind == "shell"
    assert fact.handoff.action_id is None
    idle = [item for item in attention if item.id == "hygiene:idle-factory:repo"]
    assert [item.handoff.action_id for item in idle] == ["impl:bd-free"]
    assert "1 admission-eligible ready work-items" in idle[0].summary


def test_a_later_route_record_retires_the_fact_and_the_item_is_dispatchable_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the same hold with a retiring record after it composes nothing."""
    _fixture(
        root=tmp_path,
        records=[
            {"at": _stamp(days=1), "stage": "recovery-held", "work_item_id": "bd-held"},
            {"at": _stamp(), "stage": "recovery-route", "work_item_id": "bd-held"},
        ],
    )

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert _ids(attention=attention, prefix="hygiene:journal-hold") == []
    idle = [item for item in attention if item.id == "hygiene:idle-factory:repo"]
    assert "2 admission-eligible ready work-items" in idle[0].summary


def test_a_branch_reclaim_hold_is_reported_but_the_item_still_counts_as_eligible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`publish-branch-reclaim-held` refuses no dispatch, so the idle row still names it."""
    _fixture(
        root=tmp_path,
        records=[
            {"at": _stamp(), "stage": "publish-branch-reclaim-held", "work_item_id": "bd-held"}
        ],
    )

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert _ids(attention=attention, prefix="hygiene:journal-hold") == [
        "hygiene:journal-hold:bd-held"
    ]
    idle = [item for item in attention if item.id == "hygiene:idle-factory:repo"]
    assert [item.handoff.action_id for item in idle] == ["impl:bd-held"]


def test_a_hold_older_than_seven_days_composes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture(
        root=tmp_path,
        records=[{"at": _stamp(days=8), "stage": "recovery-held", "work_item_id": "bd-held"}],
    )

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert _ids(attention=attention, prefix="hygiene:journal-hold") == []


def test_an_unreadable_journal_is_one_unobservable_fact_and_no_idle_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not an empty hold set: nothing may be read as idle on a journal nobody could read."""
    _fixture(root=tmp_path, records=[])
    journal = tmp_path / _JOURNAL
    journal.unlink()
    journal.mkdir()

    attention = _snapshot(root=tmp_path, monkeypatch=monkeypatch)

    assert _ids(attention=attention, prefix="hygiene:journal-hold") == [
        "hygiene:journal-hold:unobservable"
    ]
    assert _ids(attention=attention, prefix="hygiene:idle-factory") == []
