"""Coverage for the `hygiene:journal-hold:<subject>` lane.

A hold that only the dispatch journal records reaches no other lane: the item
rests in `ready` with no claim and no blocked reason, so nothing is stranded,
nothing ages past a bound, and the idle-factory fact would count it dispatchable.
The lane composes one fact per subject whose newest unretired hold stage is
still current, from ONE reading of this repository's own journal, and reports an
unreadable journal as its own fact rather than as a repository holding nothing.
"""

import importlib
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_needs_attention_journal_hold.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._needs_attention_journal_hold"
_NOW = datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def _at(*, days: float = 0.0) -> str:
    return (_NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record(stage: str, *, days: float = 0.0, **fields: object) -> dict[str, object]:
    return {"at": _at(days=days), "stage": stage, **fields}


def _item(*, id_: str, status: str = "ready") -> WorkItem:
    return WorkItem(
        id=id_,
        type="task",
        status=status,  # pyright: ignore[reportArgumentType]
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


_JOURNAL_WRITES = count()


def _journal(root: Path, *, records: list[dict[str, object]]) -> Path:
    # A fresh file per call: the shared tail cache reads a longer rewrite of one
    # inode as an append, so a case that rewrote one path would read stale bytes.
    journal = root / "tmp" / f"journal-{next(_JOURNAL_WRITES)}.jsonl"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return journal


def _facts(
    root: Path, *, records: list[dict[str, object]], items: list[WorkItem] | None = None
) -> list[object]:
    journal = _journal(root, records=records)
    module = importlib.import_module(_MODULE_NAME)
    live = items if items is not None else [_item(id_="I"), _item(id_="J")]
    reading = module.read_journal_holds(journal_path=journal, items=live, now=_NOW)
    return module.journal_hold_items(project_root=root, repo="repo", items=live, reading=reading)


def _ids(facts: list[object]) -> list[str]:
    return [fact.id for fact in facts]  # pyright: ignore[reportAttributeAccessIssue]


def _summary(fact: object) -> str:
    return fact.summary  # pyright: ignore[reportAttributeAccessIssue]


def test_a_current_hold_composes_one_fact_naming_every_reason(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record(
                "recovery-held",
                work_item_id="I",
                measurements=["published-head-unreadable"],
                details=["gh failed"],
                refusals=["preserved-ref-unreadable"],
            )
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]
    fact = facts[0]
    assert fact.kind == "hygiene"  # pyright: ignore[reportAttributeAccessIssue]
    for needle in ("I", "recovery-held", "published-head-unreadable", "preserved-ref-unreadable"):
        assert needle in _summary(fact)
    handoff = fact.handoff  # pyright: ignore[reportAttributeAccessIssue]
    assert handoff.kind == "shell"
    assert handoff.action_id is None
    assert "fabro-dispatch-journal.jsonl" in handoff.command
    assert "recovery-held" in handoff.command


def test_a_hold_naming_only_a_run_takes_the_run_as_its_subject(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(tmp_path, records=[_record("orphan-run-reconcile-held", run_id="R", reason="x")])

    assert _ids(facts) == ["hygiene:journal-hold:R"]


def test_a_later_retiring_record_removes_the_fact(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", days=1, work_item_id="I"),
            _record("recovery-route", work_item_id="I"),
        ],
    )

    assert facts == []


def test_a_record_with_no_retiring_stage_leaves_the_hold_current(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", work_item_id="I"),
            _record("pr-view", work_item_id="I"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]


def test_a_hold_older_than_seven_days_composes_nothing_and_reports_nothing_resolved(
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(tmp_path, records=[_record("recovery-held", days=8, work_item_id="I")])

    assert facts == []


def test_a_hold_inside_the_window_is_still_current(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(tmp_path, records=[_record("recovery-held", days=6, work_item_id="I")])

    assert _ids(facts) == ["hygiene:journal-hold:I"]


def test_a_closed_items_hold_retires(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[_record("recovery-held", work_item_id="I")],
        items=[_item(id_="I", status="done")],
    )

    assert facts == []


def test_an_unreadable_journal_is_unobservable_rather_than_empty(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    journal.mkdir(parents=True)

    reading = module.read_journal_holds(journal_path=journal, items=[], now=_NOW)
    facts = module.journal_hold_items(project_root=tmp_path, repo="repo", items=[], reading=reading)

    assert reading.observable is False
    assert _ids(facts) == ["hygiene:journal-hold:unobservable"]
    assert "cannot be read" in _summary(facts[0])


def test_an_absent_journal_is_observable_and_holds_nothing(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)

    reading = module.read_journal_holds(
        journal_path=tmp_path / "tmp" / "fabro-dispatch-journal.jsonl", items=[], now=_NOW
    )

    assert reading.observable is True
    assert reading.holds == ()


def test_an_excluded_record_of_one_stage_does_not_hide_a_hold_of_another(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", days=3, work_item_id="I"),
            _record("stranded-claim-hold", days=2, work_item_id="I", reason="run-succeeded"),
            _record("stranded-claim-hold", days=1, work_item_id="I", reason="run-live"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]
    assert "recovery-held" in _summary(facts[0])
    assert "stranded-claim-hold" not in _summary(facts[0])


def test_a_lifted_launcher_hold_ends_only_the_launcher_hold(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", days=3, work_item_id="I"),
            _record("launcher-hold", days=2, work_item_id="I", hold="hold-gmktec", reason="wip"),
            _record("launcher-hold-lifted", days=1, work_item_id="I", hold="hold-gmktec"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]
    assert "recovery-held" in _summary(facts[0])


def test_a_launcher_hold_composes_from_the_journal_and_never_from_launcher_files(
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    (tmp_path / "hold-gmktec").write_text("J\n", encoding="utf-8")
    (tmp_path / "tmp" / "tickets").mkdir(parents=True)
    (tmp_path / "tmp" / "tickets" / "J.ticket").write_text("J\n", encoding="utf-8")

    facts = _facts(
        tmp_path,
        records=[_record("launcher-hold", work_item_id="I", hold="hold-gmktec", reason="busy")],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]


def test_a_launcher_hold_without_an_item_takes_its_hold_name_and_retires_when_lifted(
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    held = _facts(
        tmp_path, records=[_record("launcher-hold", hold="hold-repo-x", reason="credential")]
    )
    lifted = _facts(
        tmp_path,
        records=[
            _record("launcher-hold", days=1, hold="hold-repo-x", reason="credential"),
            _record("launcher-hold-lifted", hold="hold-repo-x"),
        ],
    )

    assert _ids(held) == ["hygiene:journal-hold:hold-repo-x"]
    assert lifted == []


def test_a_stranded_claim_hold_whose_owner_is_live_composes_nothing(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    for reason in ("run-live", "dispatch-live", "claim-changed"):
        facts = _facts(
            tmp_path,
            records=[
                _record("stranded-claim-hold", days=2, work_item_id="I", reason="x-unobservable"),
                _record("stranded-claim-hold", days=1, work_item_id="I", reason=reason),
            ],
        )
        assert facts == [], reason


def test_two_held_stages_on_one_subject_compose_one_fact_from_the_newest(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", days=2, work_item_id="I"),
            _record("stranded-claim-hold", days=1, work_item_id="I", reason="run-succeeded"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]
    assert "stranded-claim-hold" in _summary(facts[0])
    assert "run-succeeded" in _summary(facts[0])


def test_a_repeated_stage_is_one_hold_read_from_its_newest_record(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("run-wall-budget-held", days=9, work_item_id="I", failed_measurement="old"),
            _record("run-wall-budget-held", days=1, work_item_id="I", failed_measurement="new"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]
    assert "new" in _summary(facts[0])
    assert "old" not in _summary(facts[0])


def test_a_runs_terminal_record_retires_its_wall_budget_hold(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("run-wall-budget-held", days=1, work_item_id="I", failed_measurement="m"),
            _record("fabro-terminal-events", work_item_id="I"),
        ],
    )

    assert facts == []


def test_a_sandbox_container_held_for_a_live_run_composes_nothing(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("sandbox-container-held", days=2, container_name="R", hold_reason="unobserved"),
            _record("sandbox-container-held", days=1, container_name="R", hold_reason="run-live"),
        ],
    )

    assert facts == []


def test_a_sandbox_container_held_for_an_unobserved_run_composes_a_fact(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("sandbox-container-held", container_name="R", hold_reason="run-unobserved")
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:R"]
    assert "run-unobserved" in _summary(facts[0])


def test_an_already_released_release_hold_composes_nothing(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    for stage in ("stall-cancel-release-held", "provider-limit-release-held"):
        held = _facts(
            tmp_path, records=[_record(stage, work_item_id="I", reason="already-released")]
        )
        owed = _facts(tmp_path, records=[_record(stage, work_item_id="I", reason="release-failed")])
        assert held == [], stage
        assert _ids(owed) == ["hygiene:journal-hold:I"], stage


def test_every_named_hold_stage_composes_a_fact(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    stages = (
        "recovery-held",
        "publish-branch-reclaim-held",
        "run-wall-budget-held",
        "stall-cancel-release-held",
        "provider-limit-release-held",
        "stranded-claim-hold",
        "orphan-run-reconcile-held",
        "sandbox-container-held",
        "incident-proof-pointer-refused",
        "acp-availability-observed-refused",
        "launcher-hold",
    )
    for stage in stages:
        facts = _facts(tmp_path, records=[_record(stage, work_item_id="I", reason="r")])
        assert _ids(facts) == ["hygiene:journal-hold:I"], stage


def test_a_record_naming_no_subject_or_an_unknown_stage_composes_nothing(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", reason="no subject"),
            _record("recovery-held", work_item_id="", reason="empty subject"),
            _record("recovery-held", work_item_id=7, reason="non-string subject"),
            _record("something-else", work_item_id="I", reason="not a hold"),
            {"work_item_id": "I", "reason": "no stage"},
        ],
    )

    assert facts == []


def test_a_retiring_record_naming_other_subjects_leaves_the_hold(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("recovery-held", days=1, work_item_id="I"),
            _record("recovery-route", work_item_id="J", run_id="R"),
        ],
    )

    assert _ids(facts) == ["hygiene:journal-hold:I"]


def test_a_retiring_record_naming_the_subject_under_another_key_retires_the_hold(
    tmp_path: Path,
) -> None:
    assert _MODULE_PATH.is_file()
    facts = _facts(
        tmp_path,
        records=[
            _record("orphan-run-reconcile-held", days=1, run_id="R"),
            _record("orphan-run-reconciled", run_id="R", work_item_id="I"),
        ],
    )

    assert facts == []


def test_structured_reason_values_render_deterministically(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    records = [_record("recovery-held", work_item_id="I", measurements=["a", "b"], refusals=[])]

    first = _facts(tmp_path, records=records)
    second = _facts(tmp_path, records=records)

    assert [_summary(fact) for fact in first] == [_summary(fact) for fact in second]
    assert '["a", "b"]' in _summary(first[0])


def test_the_live_recovery_held_set_names_unretired_unclosed_items_only(tmp_path: Path) -> None:
    assert _MODULE_PATH.is_file()
    module = importlib.import_module(_MODULE_NAME)
    journal = _journal(
        tmp_path,
        records=[
            _record("recovery-held", days=2, work_item_id="live"),
            _record("recovery-held", days=2, work_item_id="routed"),
            _record("recovery-route", days=1, work_item_id="routed"),
            _record("recovery-held", days=8, work_item_id="old"),
            _record("recovery-held", days=1, work_item_id="gone"),
            _record("recovery-held", days=3, work_item_id="lifted"),
            _record("launcher-hold-lifted", days=2, work_item_id="lifted"),
            _record("publish-branch-reclaim-held", days=1, work_item_id="reclaim"),
        ],
    )
    items = [_item(id_=name) for name in ("live", "routed", "old", "lifted", "reclaim")]
    items.append(replace(_item(id_="gone"), status="done"))  # pyright: ignore[reportArgumentType]

    reading = module.read_journal_holds(journal_path=journal, items=items, now=_NOW)

    assert reading.live_recovery_held_ids == frozenset({"live", "lifted"})
