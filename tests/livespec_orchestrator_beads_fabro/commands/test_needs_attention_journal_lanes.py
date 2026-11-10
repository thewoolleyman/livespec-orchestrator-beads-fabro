"""Coverage for the one composition that gives three lanes a single journal reading."""

import importlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_journal_lanes"
_SPEC_HEADING = "## Effective acceptance criteria"
_DEFINITION_OF_DONE = (
    "## Definition of Done\n\n- The lane composes.\n\n" f"References: {_SPEC_HEADING}\n"
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


def _project(root: Path, *, records: list[dict[str, object]]) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": {"wip_cap": 5}}}),
        encoding="utf-8",
    )
    spec = root / "SPECIFICATION"
    spec.mkdir(parents=True, exist_ok=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_SPEC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    journal = root / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_hold_fact_and_the_idle_row_come_from_one_reading(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE_NAME)
    _project(tmp_path, records=[{"at": _now(), "stage": "recovery-held", "work_item_id": "bd-a"}])

    facts = module.journal_hold_and_idle_items(
        project_root=tmp_path,
        repo="repo",
        items=[_item(id_="bd-a", rank="a1"), _item(id_="bd-b", rank="a2")],
    )

    assert [fact.id for fact in facts] == [
        "hygiene:journal-hold:bd-a",
        "hygiene:idle-factory:repo",
    ]
    assert facts[1].handoff.action_id == "impl:bd-b"


def test_the_journal_is_read_once_for_the_three_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    _project(tmp_path, records=[])
    reads: list[Path] = []
    real = module.read_journal_holds

    def _counting(**kwargs: object) -> object:
        reads.append(kwargs["journal_path"])  # pyright: ignore[reportArgumentType]
        return real(**kwargs)

    monkeypatch.setattr(module, "read_journal_holds", _counting)

    _ = module.journal_hold_and_idle_items(
        project_root=tmp_path, repo="repo", items=[_item(id_="bd-a", rank="a1")]
    )

    assert len(reads) == 1


def test_an_unreadable_journal_reports_one_unobservable_fact_and_no_idle_row(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    _project(tmp_path, records=[])
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.unlink()
    journal.mkdir()

    facts = module.journal_hold_and_idle_items(
        project_root=tmp_path, repo="repo", items=[_item(id_="bd-a", rank="a1")]
    )

    assert [fact.id for fact in facts] == ["hygiene:journal-hold:unobservable"]
