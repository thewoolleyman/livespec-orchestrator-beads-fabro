"""Coverage for the one attention row an idle factory produces."""

import importlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_idle_factory.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_idle_factory"
_FACT_ID = "hygiene:idle-factory:repo"


def _item(*, id_: str, status: str = "ready", rank: str = "a1", **overrides: object) -> WorkItem:
    base = WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
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
    return replace(base, **overrides)  # pyright: ignore[reportArgumentType]


def _write_project(root: Path) -> None:
    (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 5}}}),
        encoding="utf-8",
    )


def _write_journal(root: Path, *, records: list[dict[str, object]]) -> None:
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _idle_factory_items(**kwargs: object) -> list[object]:
    module = importlib.import_module(_MODULE_NAME)
    return module.idle_factory_items(**kwargs)


def _admission_eligible_ready_items(**kwargs: object) -> list[WorkItem]:
    module = importlib.import_module(_MODULE_NAME)
    return module.admission_eligible_ready_items(**kwargs)


def _counted_claims(**kwargs: object) -> int:
    module = importlib.import_module(_MODULE_NAME)
    return module.counted_claims(**kwargs)


def test_an_idle_factory_with_ready_work_composes_one_high_urgency_dispatch_row(
    tmp_path: Path,
) -> None:
    """The whole trigger in one case: one row, high urgency, the first ranked dispatch."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])

    attention = _idle_factory_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-second", rank="a2"), _item(id_="bd-first", rank="a1")],
    )

    assert [item.id for item in attention] == [_FACT_ID]
    row = attention[0]
    assert row.kind == "hygiene"
    assert row.urgency == "high"
    assert "2 admission-eligible ready work-items" in row.summary
    assert "bd-first" in row.summary
    assert row.source_ref.work_item == "bd-first"
    assert row.handoff.kind == "drive"
    assert row.handoff.action_id == "impl:bd-first"
    assert "--action impl:bd-first" in row.handoff.command


def test_the_row_is_byte_identical_across_two_passes_over_an_unchanged_store(
    tmp_path: Path,
) -> None:
    """No clock, dwell, or run id may reach the summary the operator reads."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])
    kwargs: dict[str, object] = {
        "project_root": tmp_path,
        "repo": "repo",
        "items": [_item(id_="bd-first")],
    }

    first = _idle_factory_items(**kwargs)
    second = _idle_factory_items(**kwargs)

    assert [item.summary for item in first] == [item.summary for item in second]
    assert [item.handoff.command for item in first] == [item.handoff.command for item in second]


def test_a_counted_claim_clears_the_row(tmp_path: Path) -> None:
    """A busy factory is not an idle one, however much ready work waits behind it."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[{"stage": "ledger-admit", "work_item_id": "bd-busy"}])
    # A counted claim is the accounting's own verdict, not the count of `active`
    # rows: a live dispatch lock is what makes this row occupy a slot.
    _ = write_dispatch_lock(repo=tmp_path, work_item_id="bd-busy", dispatch_id="run-busy")

    items = [_item(id_="bd-busy", status="active", assignee="fabro"), _item(id_="bd-first")]

    assert _counted_claims(project_root=tmp_path, items=items) == 1
    assert _idle_factory_items(project_root=tmp_path, repo="repo", items=items) == []


def test_no_admission_eligible_ready_item_clears_the_row(tmp_path: Path) -> None:
    """Nothing to dispatch is not idleness — it is an empty queue, and says nothing."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])

    assert (
        _idle_factory_items(
            project_root=tmp_path,
            repo="repo",
            items=[_item(id_="bd-backlog", status="backlog")],
        )
        == []
    )


def test_an_unexpired_provider_exhaustion_record_clears_the_row(tmp_path: Path) -> None:
    """That wait already composes its own row; a second one would double-report it."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(
        tmp_path,
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

    assert (
        _idle_factory_items(project_root=tmp_path, repo="repo", items=[_item(id_="bd-first")]) == []
    )


def test_a_host_only_item_and_a_manual_pending_item_are_not_admission_eligible(
    tmp_path: Path,
) -> None:
    """The valve's own non-capacity refusals, minus capacity: host-only and manual."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])

    eligible = _admission_eligible_ready_items(
        project_root=tmp_path,
        items=[
            _item(id_="bd-host", rank="a1", factory_safety="host-only"),
            _item(id_="bd-manual", rank="a2", status="pending-approval"),
            _item(id_="bd-ready", rank="a3"),
        ],
    )

    assert [item.id for item in eligible] == ["bd-ready"]


def test_an_auto_admission_pending_item_is_eligible_and_names_its_own_dispatch(
    tmp_path: Path,
) -> None:
    """`drive --action impl:<id>` admits and dispatches an `admission:auto` item in one step."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])

    attention = _idle_factory_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-auto", status="pending-approval", admission_policy="auto")],
    )

    assert [item.handoff.action_id for item in attention] == ["impl:bd-auto"]


@pytest.mark.parametrize("repo", ["", "12"])
def test_a_repo_name_the_id_grammar_rejects_surfaces_loudly_rather_than_vanishing(
    tmp_path: Path, repo: str
) -> None:
    """A refused id costs the row its shape, never its visibility."""
    assert _MODULE_PATH.is_file()
    _write_project(tmp_path)
    _write_journal(tmp_path, records=[])

    attention = _idle_factory_items(project_root=tmp_path, repo=repo, items=[_item(id_="bd-first")])

    assert len(attention) == 1
    assert attention[0].id.startswith("hygiene:attention-invalid:")
