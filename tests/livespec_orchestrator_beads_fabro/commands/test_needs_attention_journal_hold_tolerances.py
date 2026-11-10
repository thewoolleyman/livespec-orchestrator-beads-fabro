"""Tolerances of the journal-hold lane that its main coverage cannot reach.

Each case here is a journal shape a live append-only file holds: a record the
append layer never stamped, a stamp nobody can parse, an excluded record with no
hold before it, and the two defaults a caller outside the snapshot relies on.
"""

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_journal_hold"
_NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _item(*, id_: str) -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status="ready",
        title=f"{id_} title",
        description="",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-07T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _write(root: Path, *, records: list[dict[str, object]], name: str) -> Path:
    journal = root / "tmp" / name
    journal.parent.mkdir(parents=True, exist_ok=True)
    _ = journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return journal


def test_a_record_with_no_stamp_or_an_unparseable_one_stays_current(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE_NAME)
    journal = _write(
        tmp_path,
        name="unstamped.jsonl",
        records=[
            {"stage": "recovery-held", "work_item_id": "I"},
            {"stage": "recovery-held", "work_item_id": "J", "at": "yesterday-ish"},
            {"stage": "recovery-held", "work_item_id": "K", "at": 7},
        ],
    )

    reading = module.read_journal_holds(journal_path=journal, items=[], now=_NOW)

    assert [hold.subject for hold in reading.holds] == ["I", "J", "K"]
    assert reading.live_recovery_held_ids == frozenset({"I", "J", "K"})


def test_an_excluded_record_with_no_earlier_hold_composes_nothing(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE_NAME)
    journal = _write(
        tmp_path,
        name="excluded.jsonl",
        records=[
            {
                "at": "2026-11-10T11:00:00Z",
                "stage": "stranded-claim-hold",
                "work_item_id": "I",
                "reason": "run-live",
            }
        ],
    )

    reading = module.read_journal_holds(journal_path=journal, items=[], now=_NOW)

    assert reading.holds == ()
    assert reading.observable is True


def test_a_reading_taken_with_no_instant_measures_age_against_the_clock(tmp_path: Path) -> None:
    module = importlib.import_module(_MODULE_NAME)
    stale = _write(
        tmp_path,
        name="stale.jsonl",
        records=[{"at": "2001-01-01T00:00:00Z", "stage": "recovery-held", "work_item_id": "I"}],
    )
    fresh_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = _write(
        tmp_path,
        name="fresh.jsonl",
        records=[{"at": fresh_stamp, "stage": "recovery-held", "work_item_id": "I"}],
    )

    assert module.read_journal_holds(journal_path=stale, items=[]).holds == ()
    assert [
        hold.subject for hold in module.read_journal_holds(journal_path=fresh, items=[]).holds
    ] == ["I"]


def test_the_facts_read_this_repositorys_own_journal_when_no_reading_is_supplied(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE_NAME)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    _ = _write(
        tmp_path,
        name="fabro-dispatch-journal.jsonl",
        records=[{"at": stamp, "stage": "recovery-held", "work_item_id": "I"}],
    )

    facts = module.journal_hold_items(project_root=tmp_path, repo="repo", items=[_item(id_="I")])

    assert [fact.id for fact in facts] == ["hygiene:journal-hold:I"]
    assert facts[0].source_ref.work_item == "I"
